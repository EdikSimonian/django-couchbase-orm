import SwiftUI

/// BrewSync color theme — dark brewery aesthetic matching the web UI.
enum Theme {
    // Core colors (from web CSS variables)
    static let bg = Color(hex: "1a1a2e")
    static let bgAlt = Color(hex: "16213e")
    static let card = Color(hex: "1e2a45")
    static let accent = Color(hex: "e6a117")
    static let accentLight = Color(hex: "f5c842")
    static let text = Color(hex: "e0e0e0")
    static let textMuted = Color(hex: "8a8a9a")
    static let success = Color(hex: "2ecc71")
    static let border = Color(hex: "2a2a4a")
    static let danger = Color(hex: "e74c3c")

    // Semantic
    static let starFilled = accent
    static let starEmpty = Color(hex: "3a3a5a")
}

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: .alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let r = Double((int >> 16) & 0xFF) / 255
        let g = Double((int >> 8) & 0xFF) / 255
        let b = Double(int & 0xFF) / 255
        self.init(red: r, green: g, blue: b)
    }
}
