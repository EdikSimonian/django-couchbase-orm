import SwiftUI

struct BeerCardView: View {
    let beer: Beer

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Name + ABV
            HStack(alignment: .top) {
                Text(beer.name)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white)
                    .lineLimit(2)
                Spacer()
                if let abv = beer.abv {
                    Text(String(format: "%.1f%%", abv))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(Theme.accent)
                        .foregroundColor(.black)
                        .cornerRadius(12)
                }
            }

            // Style
            if !beer.style.isEmpty {
                Text(beer.style)
                    .font(.caption)
                    .foregroundColor(Theme.accent)
            }

            // Brewery
            if let name = beer.breweryName, !name.isEmpty {
                Text(name)
                    .font(.caption)
                    .foregroundColor(Theme.textMuted)
            }

            // Description
            if !beer.description.isEmpty {
                Text(beer.description)
                    .font(.caption)
                    .foregroundColor(Theme.textMuted)
                    .lineLimit(2)
            }

            Spacer(minLength: 0)

            // Rating + IBU
            HStack {
                RatingStarsView(rating: beer.avgRating, count: beer.ratingCount)
                Spacer()
                if let ibu = beer.ibu {
                    Text("\(ibu) IBU")
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color(hex: "333"))
                        .foregroundColor(Theme.textMuted)
                        .cornerRadius(8)
                }
            }
        }
        .padding(16)
        .background(Theme.card)
        .cornerRadius(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }
}
