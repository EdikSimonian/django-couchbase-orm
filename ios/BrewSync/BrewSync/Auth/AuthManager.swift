import AuthenticationServices
import Foundation
import SwiftUI

/// Manages OIDC authentication via Couchbase App Services.
///
/// Flow: iOS → App Services _oidc → Django login → App Services _oidc_callback → session
@MainActor
class AuthManager: NSObject, ObservableObject {
    static let shared = AuthManager()

    // Django server for registration and user info
    private let djangoURL = "https://django-couchbase-orm-production.up.railway.app"

    // App Services for OIDC auth flow
    private let appServicesURL = "https://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"
    private let oidcProvider = "django"

    @Published var isAuthenticated = false
    @Published var username: String = ""
    @Published var userId: Int = 0
    @Published var isAdmin: Bool = false
    @Published var isLoading = false
    @Published var error: String?

    override init() {
        super.init()
        // Restore session from keychain
        if KeychainHelper.load(key: "sync_session") != nil,
           let name = KeychainHelper.load(key: "username") {
            self.isAuthenticated = true
            self.username = name
            self.userId = Int(KeychainHelper.load(key: "user_id") ?? "0") ?? 0
            self.isAdmin = KeychainHelper.load(key: "groups")?.contains("admin") ?? false
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
            if let body = String(data: data, encoding: .utf8) {
                throw AuthError.serverError(body)
            }
            throw AuthError.serverError("Registration failed")
        }
    }

    // MARK: - OIDC Login via App Services

    func login() async {
        isLoading = true
        error = nil

        do {
            // Step 1: Get the OIDC login URL from App Services
            let oidcURL = URL(string: "\(appServicesURL)/_oidc?provider=default&offline=true")!
            print("[Auth] Starting OIDC flow via App Services: \(oidcURL)")

            // Step 2: Follow the redirect to get Django's authorize URL
            let loginURL = try await getRedirectURL(from: oidcURL)
            print("[Auth] Got login URL: \(loginURL.absoluteString.prefix(80))...")

            // Step 3: Open browser for user to login at Django
            let callbackURL = try await openBrowser(url: loginURL)
            print("[Auth] Got callback: \(callbackURL.absoluteString.prefix(80))...")

            // Step 4: The callback URL is App Services' _oidc_callback with session info
            // Parse the session from the response
            try await handleCallback(callbackURL: callbackURL)

        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            self.error = nil
        } catch {
            self.error = error.localizedDescription
            print("[Auth] Error: \(error)")
        }

        isLoading = false
    }

    /// Follow redirect from App Services _oidc to get the actual login URL
    private func getRedirectURL(from url: URL) async throws -> URL {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        // Use a session that doesn't follow redirects
        let config = URLSessionConfiguration.default
        let session = URLSession(configuration: config, delegate: RedirectStopper(), delegateQueue: nil)

        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 302 || httpResponse.statusCode == 301,
              let location = httpResponse.value(forHTTPHeaderField: "Location"),
              let redirectURL = URL(string: location) else {
            // If no redirect, the URL itself might be the login page
            return url
        }

        return redirectURL
    }

    /// Open browser for user login
    private func openBrowser(url: URL) async throws -> URL {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<URL, Error>) in
            let session = ASWebAuthenticationSession(
                url: url,
                callbackURLScheme: nil  // Accept any callback
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
    }

    /// Handle the callback from App Services after OIDC flow
    private func handleCallback(callbackURL: URL) async throws {
        // The callback might be the App Services _oidc_callback URL itself
        // with offline=true it returns JSON with session_id
        // Let's call it directly to get the session

        let components = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)
        let code = components?.queryItems?.first(where: { $0.name == "code" })?.value

        if let code = code {
            // We intercepted the redirect to _oidc_callback — call it ourselves
            print("[Auth] Got auth code, exchanging via App Services...")
            try await exchangeCodeViaAppServices(code: code)
        } else if let sessionID = components?.queryItems?.first(where: { $0.name == "session_id" })?.value {
            // App Services already processed and returned session in URL
            print("[Auth] Got session directly from callback")
            let name = components?.queryItems?.first(where: { $0.name == "name" })?.value ?? ""
            saveSession(sessionID: sessionID, username: name)
        } else {
            // Try parsing the callback URL as the _oidc_callback response
            throw AuthError.serverError("Could not extract session from callback")
        }
    }

    /// Exchange auth code via App Services _oidc_callback endpoint
    private func exchangeCodeViaAppServices(code: String) async throws {
        let callbackURL = "\(appServicesURL)/_oidc_callback?provider=default&code=\(code)&offline=true"
        guard let url = URL(string: callbackURL) else {
            throw AuthError.serverError("Invalid callback URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AuthError.networkError
        }

        print("[Auth] _oidc_callback response: \(httpResponse.statusCode)")
        if let body = String(data: data, encoding: .utf8) {
            print("[Auth] _oidc_callback body: \(body.prefix(300))")
        }

        guard httpResponse.statusCode == 200 else {
            let body = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw AuthError.serverError("App Services auth failed: \(body)")
        }

        // Parse JSON response: {"id_token":"...", "session_id":"...", "name":"..."}
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sessionID = json["session_id"] as? String else {
            throw AuthError.serverError("Could not parse session from App Services")
        }

        let name = json["name"] as? String ?? ""
        saveSession(sessionID: sessionID, username: name)

        // Parse ID token for groups
        if let idToken = json["id_token"] as? String {
            parseIdToken(idToken)
            KeychainHelper.save(key: "id_token", value: idToken)
        }
    }

    private func saveSession(sessionID: String, username: String) {
        KeychainHelper.save(key: "sync_session", value: sessionID)
        KeychainHelper.save(key: "username", value: username)
        self.username = username
        self.isAuthenticated = true
    }

    // MARK: - Token Parsing

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
        if let sub = claims["sub"] as? String {
            username = sub
            KeychainHelper.save(key: "username", value: sub)
        }
        if let preferredUsername = claims["preferred_username"] as? String {
            username = preferredUsername
            KeychainHelper.save(key: "username", value: preferredUsername)
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

// MARK: - Redirect Stopper (to capture redirect URL without following)

private class RedirectStopper: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        // Don't follow the redirect — we want the Location header
        completionHandler(nil)
    }
}

// MARK: - Errors

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
