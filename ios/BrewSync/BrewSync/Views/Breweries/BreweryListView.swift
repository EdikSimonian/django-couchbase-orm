import SwiftUI

struct BreweryListView: View {
    @State private var breweries: [Brewery] = []

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            ScrollView {
                LazyVStack(spacing: 12) {
                    ForEach(breweries) { brewery in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(brewery.name)
                                .font(.system(size: 17, weight: .semibold))
                                .foregroundColor(.white)
                            if !brewery.city.isEmpty {
                                HStack(spacing: 4) {
                                    Image(systemName: "mappin")
                                        .font(.caption2)
                                    Text([brewery.city, brewery.state, brewery.country]
                                        .filter { !$0.isEmpty }
                                        .joined(separator: ", "))
                                }
                                .font(.caption)
                                .foregroundColor(Theme.textMuted)
                            }
                            if !brewery.description.isEmpty {
                                Text(brewery.description)
                                    .font(.caption)
                                    .foregroundColor(Theme.textMuted)
                                    .lineLimit(2)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(16)
                        .background(Theme.card)
                        .cornerRadius(12)
                    }
                }
                .padding(.horizontal)
                .padding(.top, 8)
            }
        }
        .navigationTitle("Breweries")
        .onAppear {
            breweries = DatabaseManager.shared.getAllBreweries()
        }
    }
}
