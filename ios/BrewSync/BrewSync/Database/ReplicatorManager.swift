import Foundation
import CouchbaseLiteSwift

/// Manages continuous replication to Couchbase Capella App Services.
class ReplicatorManager: ObservableObject {
    static let shared = ReplicatorManager()

    private let appServicesWSS = "wss://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"
    private let appServicesHTTPS = "https://lcqfknrvnr1vpm5x.apps.cloud.couchbase.com:4984/brewsync"
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

    /// Get the OIDC login URL from App Services (for use in ASWebAuthenticationSession)
    var oidcLoginURL: URL? {
        URL(string: "\(appServicesHTTPS)/_oidc?provider=\(oidcProviderName)&offline=true")
    }

    /// Start replication with a session ID obtained from App Services OIDC flow
    func start(sessionID: String? = nil) {
        guard DatabaseManager.shared.database != nil else {
            print("[Replicator] Database not initialized")
            return
        }

        guard let url = URL(string: appServicesWSS) else { return }

        // Use provided session or try stored one
        let session = sessionID ?? KeychainHelper.load(key: "sync_session")
        guard let session = session, !session.isEmpty else {
            print("[Replicator] No sync session available")
            status = .error
            return
        }

        // Save for reconnection
        KeychainHelper.save(key: "sync_session", value: session)

        let endpoint = URLEndpoint(url: url)
        var collections: [Collection] = []
        if let c = DatabaseManager.shared.beerCollection { collections.append(c) }
        if let c = DatabaseManager.shared.breweryCollection { collections.append(c) }
        if let c = DatabaseManager.shared.ratingCollection { collections.append(c) }
        if let c = DatabaseManager.shared.blogPageCollection { collections.append(c) }
        print("[Replicator] Syncing \(collections.count) collections")

        var config = ReplicatorConfiguration(target: endpoint)
        config.replicatorType = .pushAndPull
        config.continuous = true
        config.addCollections(collections)
        config.authenticator = SessionAuthenticator(sessionID: session, cookieName: "SyncGatewaySession")

        print("[Replicator] Starting with session: \(session.prefix(20))...")
        print("[Replicator] Collections: \(collections.map { $0.name })")

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
                    let beers = DatabaseManager.shared.getAllBeers().count
                    let breweries = DatabaseManager.shared.getAllBreweries().count
                    let blogs = DatabaseManager.shared.getAllBlogPosts().count
                    // Count wagtailcore_page docs
                    var pageCount = 0
                    if let col = DatabaseManager.shared.wagtailPageCollection {
                        let q = QueryBuilder.select(SelectResult.expression(Meta.id)).from(DataSource.collection(col))
                        pageCount = (try? q.execute().allResults().count) ?? 0
                    }
                    print("[Replicator] Idle — synced \(change.status.progress.completed) docs | Local: \(beers) beers, \(breweries) breweries, \(blogs) blogs, \(pageCount) pages")
                case .busy:
                    self?.status = .connected
                    self?.isConnected = true
                    print("[Replicator] Busy — \(change.status.progress.completed)/\(change.status.progress.total)")
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
                    self?.status = .error
                }
            }
        }

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
