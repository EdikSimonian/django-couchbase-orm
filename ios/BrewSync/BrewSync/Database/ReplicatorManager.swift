import Foundation
import CouchbaseLiteSwift

/// Manages continuous replication to Couchbase Capella App Services.
class ReplicatorManager: ObservableObject {
    static let shared = ReplicatorManager()

    private let appServicesURL = "wss://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"

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

        // Collect all collections to sync
        var collections: [Collection] = []
        if let c = DatabaseManager.shared.beerCollection { collections.append(c) }
        if let c = DatabaseManager.shared.breweryCollection { collections.append(c) }
        if let c = DatabaseManager.shared.ratingCollection { collections.append(c) }

        var config = ReplicatorConfiguration(target: endpoint)
        config.replicatorType = .pushAndPull
        config.continuous = true
        config.addCollections(collections)

        // Authenticate with OIDC bearer token
        config.headers = ["Authorization": "Bearer \(idToken)"]

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
                    print("[Replicator] Error: \(error)")
                    print("[Replicator] Error description: \(error.localizedDescription)")
                    print("[Replicator] Activity: \(change.status.activity)")
                    print("[Replicator] Progress: \(change.status.progress.completed)/\(change.status.progress.total)")
                    self?.status = .error
                }
            }
        }

        print("[Replicator] Starting with URL: \(appServicesURL)")
        print("[Replicator] Collections: \(collections.map { $0.name })")
        print("[Replicator] Token (first 20 chars): \(String(idToken.prefix(20)))...")

        replicator?.start()
        status = .connecting
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
