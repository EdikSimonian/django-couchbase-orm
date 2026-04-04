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
        if let name = KeychainHelper.load(key: "username"), !name.isEmpty,
           KeychainHelper.load(key: "id_token") != nil {
            self.isAuthenticated = true
            self.username = name
            self.userId = Int(KeychainHelper.load(key: "user_id") ?? "0") ?? 0
            self.isAdmin = KeychainHelper.load(key: "groups")?.contains("admin") ?? false
        }
    }

    // MARK: - Refresh session on app launch

    /// Get a fresh App Services session using the stored ID token.
    /// Call this on every app launch before starting the replicator.
    func refreshSession() async -> String? {
        guard let idToken = KeychainHelper.load(key: "id_token") else {
            print("[Auth] No stored ID token, need full login")
            return nil
        }

        // Check if ID token is expired
        if isTokenExpired(idToken) {
            print("[Auth] ID token expired, need full login")
            // Try refresh token first
            if let newIdToken = await refreshDjangoToken() {
                print("[Auth] Refreshed Django tokens")
                parseIdToken(newIdToken)
                KeychainHelper.save(key: "id_token", value: newIdToken)
                return await getNewSession(idToken: newIdToken)
            }
            return nil
        }

        return await getNewSession(idToken: idToken)
    }

    private func getNewSession(idToken: String) async -> String? {
        do {
            let session = try await getAppServicesSession(idToken: idToken)
            KeychainHelper.save(key: "sync_session", value: session)
            print("[Auth] Got fresh session: \(session.prefix(20))...")
            return session
        } catch {
            print("[Auth] Failed to refresh session: \(error)")
            return nil
        }
    }

    private func isTokenExpired(_ token: String) -> Bool {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return true }
        var payload = String(parts[1])
        while payload.count % 4 != 0 { payload += "=" }
        let base64 = payload
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        guard let data = Data(base64Encoded: base64),
              let claims = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let exp = claims["exp"] as? TimeInterval else { return true }
        return Date().timeIntervalSince1970 >= exp
    }

    // MARK: - Refresh Django token

    private func refreshDjangoToken() async -> String? {
        guard let refreshToken = KeychainHelper.load(key: "refresh_token") else { return nil }

        let url = URL(string: "\(djangoURL)/o/token/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let body = "grant_type=refresh_token&refresh_token=\(refreshToken)&client_id=\(clientId)"
        request.httpBody = body.data(using: .utf8)

        guard let (data, response) = try? await URLSession.shared.data(for: request),
              let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            print("[Auth] Django token refresh failed")
            return nil
        }

        if let tokenResponse = try? JSONDecoder().decode(FullTokenResponse.self, from: data) {
            KeychainHelper.save(key: "access_token", value: tokenResponse.accessToken)
            if let refresh = tokenResponse.refreshToken {
                KeychainHelper.save(key: "refresh_token", value: refresh)
            }
            return tokenResponse.idToken
        }
        return nil
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

            let tokens = try await exchangeCode(code: code)
            print("[Auth] Got tokens from Django")

            // Store all tokens
            KeychainHelper.save(key: "id_token", value: tokens.idToken)
            KeychainHelper.save(key: "access_token", value: tokens.accessToken)
            if let refresh = tokens.refreshToken {
                KeychainHelper.save(key: "refresh_token", value: refresh)
            }

            parseIdToken(tokens.idToken)

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

    private func exchangeCode(code: String) async throws -> FullTokenResponse {
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

        return try JSONDecoder().decode(FullTokenResponse.self, from: data)
    }

    // MARK: - Get App Services session

    private func getAppServicesSession(idToken: String) async throws -> String {
        // Method that works: _session with Bearer auth
        let url = URL(string: "\(appServicesURL)/_session")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(idToken)", forHTTPHeaderField: "Authorization")
        request.httpBody = "{}".data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        let httpResponse = response as? HTTPURLResponse
        let status = httpResponse?.statusCode ?? 0

        guard status == 200 else {
            throw AuthError.serverError("_session failed (\(status))")
        }

        // Extract from Set-Cookie header
        if let setCookie = httpResponse?.value(forHTTPHeaderField: "Set-Cookie"),
           let range = setCookie.range(of: "SyncGatewaySession=") {
            let afterPrefix = setCookie[range.upperBound...]
            let sessionValue = String(afterPrefix.prefix(while: { $0 != ";" }))
            if !sessionValue.isEmpty {
                return sessionValue
            }
        }

        // Try cookies stored by URLSession
        if let cookies = HTTPCookieStorage.shared.cookies(for: url) {
            for cookie in cookies where cookie.name == "SyncGatewaySession" {
                return cookie.value
            }
        }

        // Try JSON body
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let sessionID = json["session_id"] as? String {
            return sessionID
        }

        throw AuthError.serverError("No session cookie in response")
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

    // MARK: - Sign in with Apple

    func loginWithApple(idToken: String, fullName: String?) async {
        isLoading = true
        error = nil

        do {
            let tokens = try await exchangeSocialToken(
                provider: "apple",
                idToken: idToken,
                fullName: fullName
            )
            try await finishSocialLogin(tokens: tokens)
        } catch {
            self.error = error.localizedDescription
            print("[Auth] Apple login error: \(error)")
        }

        isLoading = false
    }

    // MARK: - Sign in with Google

    func loginWithGoogle(idToken: String) async {
        isLoading = true
        error = nil

        do {
            let tokens = try await exchangeSocialToken(
                provider: "google",
                idToken: idToken,
                fullName: nil
            )
            try await finishSocialLogin(tokens: tokens)
        } catch {
            self.error = error.localizedDescription
            print("[Auth] Google login error: \(error)")
        }

        isLoading = false
    }

    // MARK: - Social token exchange

    private func exchangeSocialToken(provider: String, idToken: String, fullName: String?) async throws -> FullTokenResponse {
        let url = URL(string: "\(djangoURL)/api/auth/social/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        var body: [String: Any] = [
            "provider": provider,
            "id_token": idToken,
        ]
        if let fullName = fullName, !fullName.isEmpty {
            body["full_name"] = fullName
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            let responseBody = String(data: data, encoding: .utf8) ?? ""
            print("[Auth] Social token exchange failed: \(responseBody)")
            throw AuthError.tokenExchangeFailed
        }

        return try JSONDecoder().decode(FullTokenResponse.self, from: data)
    }

    private func finishSocialLogin(tokens: FullTokenResponse) async throws {
        KeychainHelper.save(key: "id_token", value: tokens.idToken)
        KeychainHelper.save(key: "access_token", value: tokens.accessToken)
        if let refresh = tokens.refreshToken {
            KeychainHelper.save(key: "refresh_token", value: refresh)
        }

        parseIdToken(tokens.idToken)

        let sessionID = try await getAppServicesSession(idToken: tokens.idToken)
        KeychainHelper.save(key: "sync_session", value: sessionID)
        isAuthenticated = true
        print("[Auth] Social login complete, session: \(sessionID.prefix(20))...")
    }

    // MARK: - Logout

    func logout() {
        KeychainHelper.clearAll()
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

private struct FullTokenResponse: Codable {
    let accessToken: String
    let idToken: String
    let refreshToken: String?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case idToken = "id_token"
        case refreshToken = "refresh_token"
    }
}

enum AuthError: LocalizedError, Equatable {
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
