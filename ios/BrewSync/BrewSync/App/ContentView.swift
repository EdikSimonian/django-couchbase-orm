import SwiftUI
import CouchbaseLiteSwift

struct ContentView: View {
    @ObservedObject var auth = AuthManager.shared
    @ObservedObject var replicator = ReplicatorManager.shared

    var body: some View {
        ZStack {
            if auth.isAuthenticated {
                TabView {
                    BeerListView()
                        .tabItem {
                            Label("Beers", systemImage: "mug.fill")
                        }
                    BreweryListView()
                        .tabItem {
                            Label("Breweries", systemImage: "building.2")
                        }
                }
                .tint(Theme.accent)

                // Offline indicator
                if !replicator.isConnected && replicator.status != .stopped {
                    VStack {
                        HStack(spacing: 6) {
                            Image(systemName: "wifi.slash")
                                .font(.caption2)
                            Text(replicator.status.rawValue)
                                .font(.caption2)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(Theme.card)
                        .foregroundColor(Theme.textMuted)
                        .cornerRadius(20)
                        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Theme.border, lineWidth: 1))
                        Spacer()
                    }
                    .padding(.top, 4)
                }
            } else {
                LoginView()
            }
        }
        .preferredColorScheme(.dark)
        .onAppear {
            // Enable verbose Couchbase Lite logging
            Database.log.console.domains = .all
            Database.log.console.level = .verbose
            print("[App] CouchbaseLite verbose logging enabled")
        }
        .onChange(of: auth.isAuthenticated) { authenticated in
            if authenticated {
                print("[App] Authenticated as \(auth.username), admin=\(auth.isAdmin)")
                print("[App] Session: \(KeychainHelper.load(key: "sync_session")?.prefix(30) ?? "none")...")
                do {
                    try DatabaseManager.shared.initialize()
                    print("[App] Database initialized")
                    print("[App] Beer collection: \(DatabaseManager.shared.beerCollection?.name ?? "nil")")
                    print("[App] Brewery collection: \(DatabaseManager.shared.breweryCollection?.name ?? "nil")")
                    print("[App] Rating collection: \(DatabaseManager.shared.ratingCollection?.name ?? "nil")")
                    ReplicatorManager.shared.start()
                } catch {
                    print("[App] Database init FAILED: \(error)")
                }
            } else {
                print("[App] Logged out")
                ReplicatorManager.shared.stop()
                DatabaseManager.shared.close()
            }
        }
    }
}
