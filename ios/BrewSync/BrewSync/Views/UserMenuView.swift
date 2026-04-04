import SwiftUI

struct UserMenuView: View {
    @ObservedObject var auth = AuthManager.shared
    @State private var showDeleteConfirmation = false

    var body: some View {
        Menu {
            Text("Signed in as \(auth.username)")
            if auth.isAdmin {
                Label("Admin", systemImage: "shield.checkered")
            }
            Divider()
            Button("Reset Sync Data") {
                DatabaseManager.shared.deleteAndReset()
                try? DatabaseManager.shared.initialize()
                Task {
                    ReplicatorManager.shared.stop()
                    if let s = await auth.refreshSession() {
                        ReplicatorManager.shared.start(sessionID: s)
                    }
                }
            }
            Button("Sign Out", role: .destructive) {
                auth.logout()
            }
            if !auth.isAdmin {
                Divider()
                Button("Delete Account", role: .destructive) {
                    showDeleteConfirmation = true
                }
            }
        } label: {
            Image(systemName: "person.circle")
                .font(.title3)
                .foregroundColor(Theme.textMuted)
        }
        .alert("Delete Account?", isPresented: $showDeleteConfirmation) {
            Button("Cancel", role: .cancel) { }
            Button("Delete", role: .destructive) {
                Task {
                    ReplicatorManager.shared.stop()
                    do {
                        try await auth.deleteAccount()
                    } catch {
                        // Even if server delete fails, log out locally
                        print("[Auth] Delete account error: \(error)")
                        auth.logout()
                    }
                    DatabaseManager.shared.deleteAndReset()
                }
            }
        } message: {
            Text("This will permanently delete your account, ratings, and all associated data. This cannot be undone.")
        }
    }
}
