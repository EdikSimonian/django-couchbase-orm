import AuthenticationServices
import Foundation
import SwiftUI

/// Manages OIDC authentication against the Django server.
@MainActor
class AuthManager: NSObject, ObservableObject {
    static let shared = AuthManager()

    // OIDC configuration
    private let baseURL = "https://django-couchbase-orm-production.up.railway.app"
    private let clientId = "brewsync-ios"
    private let redirectURI = "brewsync://callback"
    private let scopes = "openid profile email"

    @Published var isAuthenticated = false
    @Published var username: String = ""
    @Published var userId: Int = 0
    @Published var isAdmin: Bool = false
    @Published var isLoading = false
    @Published var error: String?

    private var codeVerifier: String = ""

    override init() {
        super.init()
        // Restore session from keychain
        if let token = KeychainHelper.load(key: "access_token"),
           let name = KeychainHelper.load(key: "username") {
            self.isAuthenticated = true
            self.username = name
            self.userId = Int(KeychainHelper.load(key: "user_id") ?? "0") ?? 0
            self.isAdmin = KeychainHelper.load(key: "groups")?.contains("admin") ?? false
        }
    }

    // MARK: - Registration

    func register(username: String, email: String, password: String) async throws {
        let url = URL(string: "\(baseURL)/api/auth/register/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode([
            "username": username,
            "email": email,
            "password": password,
        ])

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.networkError
        }
        if httpResponse.statusCode != 201 {
            if let body = try? JSONDecoder().decode([String: String].self, from: data),
               let detail = body["detail"] ?? body["username"] {
                throw AuthError.serverError(detail)
            }
            throw AuthError.serverError("Registration failed (status \(httpResponse.statusCode))")
        }
    }

    // MARK: - OIDC Login

    func login() async {
        isLoading = true
        error = nil

        // Generate PKCE
        codeVerifier = generateCodeVerifier()
        let codeChallenge = generateCodeChallenge(from: codeVerifier)

        // Build authorization URL
        var components = URLComponents(string: "\(baseURL)/o/authorize/")!
        components.queryItems = [
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "client_id", value: clientId),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "scope", value: scopes),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
        ]

        guard let authURL = components.url else {
            error = "Failed to build auth URL"
            isLoading = false
            return
        }

        // Open ASWebAuthenticationSession
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

            // Extract authorization code
            guard let code = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)?
                .queryItems?.first(where: { $0.name == "code" })?.value else {
                throw AuthError.noCode
            }

            // Exchange code for tokens
            try await exchangeCodeForTokens(code: code)

        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            self.error = nil // User cancelled, not an error
        } catch {
            self.error = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - Token Exchange

    private func exchangeCodeForTokens(code: String) async throws {
        let url = URL(string: "\(baseURL)/o/token/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let body = [
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirectURI,
            "client_id": clientId,
            "code_verifier": codeVerifier,
        ]
        request.httpBody = body.map { "\($0.key)=\($0.value)" }
            .joined(separator: "&")
            .data(using: .utf8)

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw AuthError.tokenExchangeFailed
        }

        let tokenResponse = try JSONDecoder().decode(TokenResponse.self, from: data)

        // Save tokens
        KeychainHelper.save(key: "access_token", value: tokenResponse.accessToken)
        if let refresh = tokenResponse.refreshToken {
            KeychainHelper.save(key: "refresh_token", value: refresh)
        }
        if let idToken = tokenResponse.idToken {
            KeychainHelper.save(key: "id_token", value: idToken)
            parseIdToken(idToken)
        }

        // Fetch user info
        try await fetchUserInfo(accessToken: tokenResponse.accessToken)

        isAuthenticated = true
    }

    // MARK: - User Info

    private func fetchUserInfo(accessToken: String) async throws {
        let url = URL(string: "\(baseURL)/o/userinfo/")!
        var request = URLRequest(url: url)
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        let (data, _) = try await URLSession.shared.data(for: request)
        if let userInfo = try? JSONDecoder().decode(UserInfo.self, from: data) {
            username = userInfo.preferredUsername ?? ""
            userId = Int(userInfo.sub) ?? 0
            isAdmin = userInfo.groups?.contains("admin") ?? false

            KeychainHelper.save(key: "username", value: username)
            KeychainHelper.save(key: "user_id", value: String(userId))
            KeychainHelper.save(key: "groups", value: (userInfo.groups ?? []).joined(separator: ","))
        }
    }

    // MARK: - Token Refresh

    func refreshTokenIfNeeded() async -> Bool {
        guard let refreshToken = KeychainHelper.load(key: "refresh_token") else { return false }

        let url = URL(string: "\(baseURL)/o/token/")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")

        let body = [
            "grant_type": "refresh_token",
            "refresh_token": refreshToken,
            "client_id": clientId,
        ]
        request.httpBody = body.map { "\($0.key)=\($0.value)" }
            .joined(separator: "&")
            .data(using: .utf8)

        guard let (data, response) = try? await URLSession.shared.data(for: request),
              let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200,
              let tokenResponse = try? JSONDecoder().decode(TokenResponse.self, from: data) else {
            return false
        }

        KeychainHelper.save(key: "access_token", value: tokenResponse.accessToken)
        if let refresh = tokenResponse.refreshToken {
            KeychainHelper.save(key: "refresh_token", value: refresh)
        }
        return true
    }

    // MARK: - Logout

    func logout() {
        KeychainHelper.clearAll()
        isAuthenticated = false
        username = ""
        userId = 0
        isAdmin = false
    }

    // MARK: - PKCE Helpers

    private func generateCodeVerifier() -> String {
        PKCE.generateCodeVerifier()
    }

    private func generateCodeChallenge(from verifier: String) -> String {
        PKCE.generateCodeChallenge(from: verifier)
    }

    // MARK: - ID Token Parsing

    private func parseIdToken(_ token: String) {
        let parts = token.split(separator: ".")
        guard parts.count >= 2 else { return }
        var payload = String(parts[1])
        // Pad base64
        while payload.count % 4 != 0 { payload += "=" }
        guard let data = Data(base64Encoded: payload),
              let claims = try? JSONDecoder().decode(IdTokenClaims.self, from: data) else { return }
        isAdmin = claims.groups?.contains("admin") ?? false
    }
}

// MARK: - ASWebAuthenticationPresentationContextProviding

extension AuthManager: ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        ASPresentationAnchor()
    }
}

// MARK: - Response Models

private struct TokenResponse: Codable {
    let accessToken: String
    let tokenType: String
    let refreshToken: String?
    let idToken: String?
    let expiresIn: Int?
    let scope: String?

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case refreshToken = "refresh_token"
        case idToken = "id_token"
        case expiresIn = "expires_in"
        case scope
    }
}

private struct UserInfo: Codable {
    let sub: String
    let preferredUsername: String?
    let email: String?
    let groups: [String]?

    enum CodingKeys: String, CodingKey {
        case sub
        case preferredUsername = "preferred_username"
        case email, groups
    }
}

private struct IdTokenClaims: Codable {
    let sub: String?
    let groups: [String]?
}

enum AuthError: LocalizedError {
    case networkError
    case serverError(String)
    case cancelled
    case noCode
    case tokenExchangeFailed

    var errorDescription: String? {
        switch self {
        case .networkError: return "Network error"
        case .serverError(let msg): return msg
        case .cancelled: return "Login cancelled"
        case .noCode: return "No authorization code received"
        case .tokenExchangeFailed: return "Failed to exchange code for tokens"
        }
    }
}
