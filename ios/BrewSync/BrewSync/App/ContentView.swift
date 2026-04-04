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
            Database.log.console.domains = .all
            Database.log.console.level = .warning
            // Initialize DB once on app start — never close during lifecycle
            try? DatabaseManager.shared.initialize()
        }
        .task {
            if auth.isAuthenticated {
                await startReplicator()
            }
        }
        .onChange(of: auth.isAuthenticated) { authenticated in
            if authenticated {
                Task { await startReplicator() }
            } else {
                ReplicatorManager.shared.stop()
            }
        }
    }

    private func startReplicator() async {
        if let session = await AuthManager.shared.refreshSession() {
            ReplicatorManager.shared.start(sessionID: session)
        } else {
            print("[App] Session refresh failed, need re-login")
            AuthManager.shared.logout()
        }
    }
}
