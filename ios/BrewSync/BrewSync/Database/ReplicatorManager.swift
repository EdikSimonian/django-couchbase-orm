import Foundation
import CouchbaseLiteSwift

/// Manages continuous replication to Couchbase Capella App Services.
class ReplicatorManager: ObservableObject {
    static let shared = ReplicatorManager()

    private let appServicesURL = "wss://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"
    private let appServicesHTTP = "https://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"

    // The OIDC provider name as configured in Capella App Services
    private let oidcProviderName = "django"

    private var replicator: Replicator?
    private var listenerToken: ListenerToken?

    @Published var status: ReplicatorStatus = .stopped
    @Published var isConnected: Bool = false

    enum ReplicatorStatus: String {
        case stopped = "Stopped"
        case connecting = "Connecting..."
        case connected = "Connected"
        case offline = "Offline"
        case error = "Error"
    }

    private init() {}

    func start() {
        guard DatabaseManager.shared.database != nil else {
            print("[Replicator] Database not initialized")
            return
        }

        guard let idToken = KeychainHelper.load(key: "id_token") else {
            print("[Replicator] No ID token available")
            return
        }

        status = .connecting

        // Exchange the ID token for a Sync Gateway session
        Task {
            do {
                let sessionID = try await getSession(idToken: idToken)
                print("[Replicator] Got session: \(sessionID.prefix(20))...")
                await MainActor.run {
                    self.startReplicator(sessionID: sessionID)
                }
            } catch {
                print("[Replicator] Session exchange failed: \(error)")
                // Fallback: try direct basic auth if session exchange fails
                await MainActor.run {
                    self.startReplicatorWithToken(idToken: idToken)
                }
            }
        }
    }

    /// Exchange OIDC ID token for an App Services session cookie
    private func getSession(idToken: String) async throws -> String {
        // POST to _oidc_callback with the token
        let url = URL(string: "\(appServicesHTTP)/_oidc_callback?provider=\(oidcProviderName)&id_token=\(idToken)")!
        var request = URLRequest(url: url)
        request.httpMethod = "GET"

        print("[Replicator] Exchanging token at: \(appServicesHTTP)/_oidc_callback")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw ReplicatorError.sessionFailed("No HTTP response")
        }

        print("[Replicator] Session response status: \(httpResponse.statusCode)")
        if let body = String(data: data, encoding: .utf8) {
            print("[Replicator] Session response: \(body.prefix(200))")
        }

        if httpResponse.statusCode == 200 {
            // Look for SyncGatewaySession cookie
            if let cookies = HTTPCookieStorage.shared.cookies(for: url) {
                for cookie in cookies {
                    print("[Replicator] Cookie: \(cookie.name) = \(cookie.value.prefix(20))...")
                    if cookie.name == "SyncGatewaySession" {
                        return cookie.value
                    }
                }
            }

            // Also check Set-Cookie header
            if let setCookie = httpResponse.value(forHTTPHeaderField: "Set-Cookie"),
               let sessionRange = setCookie.range(of: "SyncGatewaySession=") {
                let afterPrefix = setCookie[sessionRange.upperBound...]
                let sessionValue = String(afterPrefix.prefix(while: { $0 != ";" }))
                return sessionValue
            }

            // Try parsing JSON response for session_id
            if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
               let sessionID = json["session_id"] as? String {
                return sessionID
            }
        }

        // Try POST to _session endpoint as alternative
        return try await getSessionViaPost(idToken: idToken)
    }

    /// Alternative: POST token to _session endpoint
    private func getSessionViaPost(idToken: String) async throws -> String {
        let url = URL(string: "\(appServicesHTTP)/_session")!
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: [
            "token": idToken,
            "provider": oidcProviderName,
        ])

        print("[Replicator] Trying POST _session")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw ReplicatorError.sessionFailed("No HTTP response")
        }

        print("[Replicator] _session response: \(httpResponse.statusCode)")
        if let body = String(data: data, encoding: .utf8) {
            print("[Replicator] _session body: \(body.prefix(300))")
        }

        if httpResponse.statusCode == 200,
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let sessionID = json["session_id"] as? String {
            return sessionID
        }

        // Check cookies
        if let cookies = HTTPCookieStorage.shared.cookies(for: url) {
            for cookie in cookies where cookie.name == "SyncGatewaySession" {
                return cookie.value
            }
        }

        throw ReplicatorError.sessionFailed("Could not get session (status \(httpResponse.statusCode))")
    }

    private func startReplicator(sessionID: String) {
        guard let url = URL(string: appServicesURL) else { return }

        let endpoint = URLEndpoint(url: url)
        var collections: [Collection] = []
        if let c = DatabaseManager.shared.beerCollection { collections.append(c) }
        if let c = DatabaseManager.shared.breweryCollection { collections.append(c) }
        if let c = DatabaseManager.shared.ratingCollection { collections.append(c) }

        var config = ReplicatorConfiguration(target: endpoint)
        config.replicatorType = .pushAndPull
        config.continuous = true
        config.addCollections(collections)
        config.authenticator = SessionAuthenticator(sessionID: sessionID)

        print("[Replicator] Starting with SessionAuthenticator")
        configureAndStart(config: config)
    }

    /// Fallback: try with token in headers
    private func startReplicatorWithToken(idToken: String) {
        guard let url = URL(string: appServicesURL) else { return }

        let endpoint = URLEndpoint(url: url)
        var collections: [Collection] = []
        if let c = DatabaseManager.shared.beerCollection { collections.append(c) }
        if let c = DatabaseManager.shared.breweryCollection { collections.append(c) }
        if let c = DatabaseManager.shared.ratingCollection { collections.append(c) }

        var config = ReplicatorConfiguration(target: endpoint)
        config.replicatorType = .pushAndPull
        config.continuous = true
        config.addCollections(collections)
        config.headers = ["Authorization": "Bearer \(idToken)"]

        print("[Replicator] Fallback: Starting with Bearer token header")
        configureAndStart(config: config)
    }

    private func configureAndStart(config: ReplicatorConfiguration) {
        replicator = Replicator(config: config)

        listenerToken = replicator?.addChangeListener { [weak self] change in
            DispatchQueue.main.async {
                switch change.status.activity {
                case .stopped:
                    self?.status = .stopped
                    self?.isConnected = false
                case .idle:
                    self?.status = .connected
                    self?.isConnected = true
                case .busy:
                    self?.status = .connected
                    self?.isConnected = true
                case .connecting:
                    self?.status = .connecting
                    self?.isConnected = false
                case .offline:
                    self?.status = .offline
                    self?.isConnected = false
                @unknown default:
                    break
                }

                if let error = change.status.error {
                    print("[Replicator] Error: \(error)")
                    print("[Replicator] Activity: \(change.status.activity)")
                    print("[Replicator] Progress: \(change.status.progress.completed)/\(change.status.progress.total)")
                    self?.status = .error
                }

                if change.status.activity == .idle {
                    print("[Replicator] Synced: \(change.status.progress.completed) docs")
                }
            }
        }

        replicator?.start()
    }

    func stop() {
        if let token = listenerToken {
            token.remove()
            listenerToken = nil
        }
        replicator?.stop()
        replicator = nil
        status = .stopped
        isConnected = false
    }
}

enum ReplicatorError: LocalizedError {
    case sessionFailed(String)

    var errorDescription: String? {
        switch self {
        case .sessionFailed(let msg): return "Session failed: \(msg)"
        }
    }
}
