import SwiftUI

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
        .onChange(of: auth.isAuthenticated) { _, authenticated in
            if authenticated {
                // Start database and replicator
                try? DatabaseManager.shared.initialize()
                ReplicatorManager.shared.start()
            } else {
                ReplicatorManager.shared.stop()
                DatabaseManager.shared.close()
            }
        }
    }
}
