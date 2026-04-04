import AuthenticationServices
import Foundation
import SwiftUI

/// Manages OIDC authentication: login via Django, exchange token with App Services.
@MainActor
class AuthManager: NSObject, ObservableObject {
    static let shared = AuthManager()

    private let djangoURL = "https://django-couchbase-orm-production.up.railway.app"
    private let appServicesURL = "https://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"
    private let clientId = "brewsync-ios"
    private let redirectURI = "brewsync://callback"

    @Published var isAuthenticated = false
    @Published var username: String = ""
    @Published var userId: Int = 0
    @Published var isAdmin: Bool = false
    @Published var isLoading = false
    @Published var error: String?

    private var codeVerifier: String = ""

    override init() {
        super.init()
        if KeychainHelper.load(key: "sync_session") != nil,
           let name = KeychainHelper.load(key: "username"), !name.isEmpty {
            self.isAuthenticated = true
            self.username = name
            self.userId = Int(KeychainHelper.load(key: "user_id") ?? "0") ?? 0
            self.isAdmin = KeychainHelper.load(key: "groups")?.contains("admin") ?? false
        }
    }

    // MARK: - Login

    func login() async {
        isLoading = true
        error = nil

        codeVerifier = PKCE.generateCodeVerifier()
        let codeChallenge = PKCE.generateCodeChallenge(from: codeVerifier)

        var components = URLComponents(string: "\(djangoURL)/o/authorize/")!
        components.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "scope", value: "openid profile email"),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]

        guard let authURL = components.url else {
            error = "Failed to build auth URL"
            isLoading = false
            return
        }

        do {
            let callbackURL = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
                let session = ASWebAuthenticationSession(
                    url: authURL,
                    callbackURLScheme: "brewsync"
                ) { url, error in
                    if let error = error {
                        continuation.resume(throwing: error)
                    } else if let url = url {
                        continuation.resume(returning: url)
                    } else {
                        continuation.resume(throwing: AuthError.cancelled)
                    }
                }
                session.prefersEphemeralWebBrowserSession = false
                session.presentationContextProvider = self
                session.start()
            }

            guard let code = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "code" })?.value else {
                throw AuthError.noCode
            }

            // Exchange code for tokens with Django
            let tokens = try await exchangeCode(code: code)
            print("[Auth] Got tokens from Django")

            // Parse ID token for user info
            parseIdToken(tokens.idToken)
            KeychainHelper.save(key: "id_token", value: tokens.idToken)

            // Try to get App Services session using the ID token
            let sessionID = try await getAppServicesSession(idToken: tokens.idToken)
            print("[Auth] Got App Services session: \(sessionID.prefix(20))...")

            KeychainHelper.save(key: "sync_session", value: sessionID)
            isAuthenticated = true

        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            self.error = nil
        } catch {
            self.error = error.localizedDescription
            print("[Auth] Error: \(error)")
        }

        isLoading = false
    }

    // MARK: - Exchange code for tokens (Django)

    private func exchangeCode(code: String) async throws -> TokenResponse {
        let url = URL(string: "\(djangoURL)/o/token/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let body = "grant_type=authorization_code&code=\(code)&redirect_uri=\(redirectURI)&client_id=\(clientId)&code_verifier=\(codeVerifier)"
        request.httpBody = body.data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let body = String(data: data, encoding: .utf8) ?? ""
            print("[Auth] Token exchange failed: \(body)")
            throw AuthError.tokenExchangeFailed
        }

        return try JSONDecoder().decode(TokenResponse.self, from: data)
    }

    // MARK: - Get App Services session

    private func getAppServicesSession(idToken: String) async throws -> String {
        // Try multiple methods to get a session

        // Method 1: _oidc_callback with id_token (implicit flow style)
        if let session = try? await tryOIDCCallbackWithToken(idToken: idToken) {
            return session
        }

        // Method 2: _session with Bearer auth
        if let session = try? await trySessionWithBearer(idToken: idToken) {
            return session
        }

        // Method 3: _oidc_challenge with token
        if let session = try? await tryOIDCChallenge(idToken: idToken) {
            return session
        }

        // Method 4: Use the ID token directly as session (some App Services configs accept this)
        print("[Auth] All session methods failed, using ID token as session")
        return idToken
    }

    private func tryOIDCCallbackWithToken(idToken: String) async throws -> String {
        // Try implicit flow: pass id_token directly to _oidc_callback
        let urlString = "\(appServicesURL)/_oidc_callback?id_token=\(idToken.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "")&offline=true"
        guard let url = URL(string: urlString) else { throw AuthError.networkError }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let body = String(data: data, encoding: .utf8) ?? ""
        print("[Auth] _oidc_callback?id_token: status=\(status) body=\(body.prefix(200))")

        guard status == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sessionID = json["session_id"] as? String else {
            throw AuthError.serverError("_oidc_callback failed (\(status))")
        }
        return sessionID
    }

    private func trySessionWithBearer(idToken: String) async throws -> String {
        let url = URL(string: "\(appServicesURL)/_session")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = "{}".data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        let httpResponse = response as? HTTPURLResponse
        let status = httpResponse?.statusCode ?? 0
        let body = String(data: data, encoding: .utf8) ?? ""
        print("[Auth] _session Bearer: status=\(status) body=\(body.prefix(200))")

        // Log all response headers for debugging
        if let headers = httpResponse?.allHeaderFields {
            print("[Auth] _session headers: \(headers)")
        }

        guard status == 200 else {
            throw AuthError.serverError("_session failed (\(status))")
        }

        // Try to get session from Set-Cookie header
        if let setCookie = httpResponse?.value(forHTTPHeaderField: "Set-Cookie") {
            print("[Auth] Set-Cookie: \(setCookie.prefix(80))...")
            if let range = setCookie.range(of: "SyncGatewaySession=") {
                let afterPrefix = setCookie[range.upperBound...]
                let sessionValue = String(afterPrefix.prefix(while: { $0 != ";" }))
                if !sessionValue.isEmpty {
                    print("[Auth] Extracted session from cookie: \(sessionValue.prefix(20))...")
                    return sessionValue
                }
            }
        }

        // Try cookies stored by URLSession
        if let cookies = HTTPCookieStorage.shared.cookies(for: url) {
            for cookie in cookies {
                print("[Auth] Cookie: \(cookie.name) = \(cookie.value.prefix(20))...")
                if cookie.name == "SyncGatewaySession" {
                    return cookie.value
                }
            }
        }

        // Try session_id from JSON body as fallback
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let sessionID = json["session_id"] as? String {
            return sessionID
        }

        throw AuthError.serverError("_session returned 200 but no session cookie found")
    }

    private func tryOIDCChallenge(idToken: String) async throws -> String {
        let url = URL(string: "\(appServicesURL)/_oidc_challenge?offline=true")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = "{}".data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        let body = String(data: data, encoding: .utf8) ?? ""
        print("[Auth] _oidc_challenge: status=\(status) body=\(body.prefix(200))")

        guard status == 200,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sessionID = json["session_id"] as? String else {
            throw AuthError.serverError("_oidc_challenge failed (\(status))")
        }
        return sessionID
    }

    // MARK: - Parse ID token

    private func parseIdToken(_ token: String) {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return }
        var payload = String(parts[1])
        while payload.count % 4 != 0 { payload += "=" }
        let base64 = payload
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        guard let data = Data(base64Encoded: base64),
              let claims = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return }

        if let groups = claims["groups"] as? [String] {
            isAdmin = groups.contains("admin")
            KeychainHelper.save(key: "groups", value: groups.joined(separator: ","))
        }
        if let preferredUsername = claims["preferred_username"] as? String {
            username = preferredUsername
            KeychainHelper.save(key: "username", value: preferredUsername)
        }
        if let sub = claims["sub"] as? String, username.isEmpty {
            username = sub
            KeychainHelper.save(key: "username", value: sub)
        }
    }

    // MARK: - Handle session (from OIDCWebView fallback)

    func handleSession(sessionID: String, username: String) {
        KeychainHelper.save(key: "sync_session", value: sessionID)
        KeychainHelper.save(key: "username", value: username)
        self.username = username
        self.isAuthenticated = true
        self.error = nil
    }

    // MARK: - Registration

    func register(username: String, email: String, password: String) async throws {
        let url = URL(string: "\(djangoURL)/api/auth/register/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode([
            "username": username,
            "email": email,
            "password": password,
        ])

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 201 else {
            let body = String(data: data, encoding: .utf8) ?? "Registration failed"
            throw NSError(domain: "Auth", code: 0, userInfo: [NSLocalizedDescriptionKey: body])
        }
    }

    // MARK: - Logout

    func logout() {
        KeychainHelper.clearAll()
        KeychainHelper.delete(key: "sync_session")
        isAuthenticated = false
        username = ""
        userId = 0
        isAdmin = false
    }
}

// MARK: - ASWebAuthenticationPresentationContextProviding

extension AuthManager: ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        ASPresentationAnchor()
    }
}

// MARK: - Models

private struct TokenResponse: Codable {
    let accessToken: String
    let idToken: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case idToken = "id_token"
    }
}

enum AuthError: LocalizedError {
    case networkError, cancelled, noCode, tokenExchangeFailed, serverError(String)

    var errorDescription: String? {
        switch self {
        case .networkError: return "Network error"
        case .cancelled: return "Login cancelled"
        case .noCode: return "No authorization code received"
        case .tokenExchangeFailed: return "Token exchange failed"
        case .serverError(let msg): return msg
        }
    }
}
