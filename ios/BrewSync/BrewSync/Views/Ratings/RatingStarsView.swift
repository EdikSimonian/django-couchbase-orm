import SwiftUI

/// Displays star rating. If `interactive`, allows tapping to rate.
struct RatingStarsView: View {
    let rating: Double
    let count: Int
    var interactive: Bool = false
    var onRate: ((Int) -> Void)?

    var body: some View {
        HStack(spacing: 4) {
            ForEach(1...5, id: \.self) { star in
                Image(systemName: star <= Int(rating.rounded()) ? "star.fill" : "star")
                    .foregroundColor(star <= Int(rating.rounded()) ? Theme.starFilled : Theme.starEmpty)
                    .font(.system(size: interactive ? 28 : 14))
                    .onTapGesture {
                        if interactive {
                            let generator = UIImpactFeedbackGenerator(style: .light)
                            generator.impactOccurred()
                            onRate?(star)
                        }
                    }
            }
            if count > 0 && !interactive {
                Text("(\(count))")
                    .font(.caption2)
                    .foregroundColor(Theme.textMuted)
            }
        }
    }
}
