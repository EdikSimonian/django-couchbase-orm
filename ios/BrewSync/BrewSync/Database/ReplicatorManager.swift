import Foundation
import CouchbaseLiteSwift

/// Manages continuous replication to Couchbase Capella App Services.
class ReplicatorManager: ObservableObject {
    static let shared = ReplicatorManager()

    // TODO: Replace with your actual App Services endpoint URL
    private let appServicesURL = "wss://YOUR_APP_SERVICES_ENDPOINT:4984/brewsync"

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
        guard let db = DatabaseManager.shared.database else {
            print("[Replicator] Database not initialized")
            return
        }

        guard let url = URL(string: appServicesURL) else {
            print("[Replicator] Invalid App Services URL")
            return
        }

        // Get the ID token for authentication
        guard let idToken = KeychainHelper.load(key: "id_token") else {
            print("[Replicator] No ID token available")
            return
        }

        let endpoint = URLEndpoint(url: url)

        var config = ReplicatorConfiguration(target: endpoint)
        config.replicatorType = .pushAndPull
        config.continuous = true

        // Add all collections
        if let beerCol = DatabaseManager.shared.beerCollection {
            config.addCollection(beerCol)
        }
        if let breweryCol = DatabaseManager.shared.breweryCollection {
            config.addCollection(breweryCol)
        }
        if let ratingCol = DatabaseManager.shared.ratingCollection {
            config.addCollection(ratingCol)
        }

        // Authenticate with the OIDC session token
        config.authenticator = SessionAuthenticator(sessionID: idToken)

        replicator = Replicator(config: config)

        // Listen for status changes
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
                    print("[Replicator] Error: \(error.localizedDescription)")
                    self?.status = .error
                }
            }
        }

        replicator?.start()
        status = .connecting
    }

    func stop() {
        if let token = listenerToken {
            replicator?.removeChangeListener(withToken: token)
            listenerToken = nil
        }
        replicator?.stop()
        replicator = nil
        status = .stopped
        isConnected = false
    }
}
