import SwiftUI
import CouchbaseLiteSwift

struct BreweryListView: View {
    @State private var breweries: [Brewery] = []
    private var queryToken: ListenerToken?

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            if breweries.isEmpty {
                VStack(spacing: 12) {
                    ProgressView()
                        .tint(Theme.accent)
                    Text("Syncing breweries...")
                        .font(.caption)
                        .foregroundColor(Theme.textMuted)
                }
            } else {
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
        }
        .navigationTitle("Breweries")
        .onAppear { startObserving() }
    }

    private func startObserving() {
        guard let collection = DatabaseManager.shared.breweryCollection else { return }

        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(collection))
            .orderBy(Ordering.property("name").ascending())

        query.addChangeListener { change in
            guard let results = change.results else { return }
            let list = results.compactMap { result -> Brewery? in
                guard let dict = result.dictionary(at: 0) else { return nil }
                let docId = result.string(at: 1) ?? ""
                return Brewery(
                    id: Int(docId) ?? 0,
                    name: dict.string(forKey: "name") ?? "",
                    city: dict.string(forKey: "city") ?? "",
                    state: dict.string(forKey: "state") ?? "",
                    country: dict.string(forKey: "country") ?? "",
                    description: dict.string(forKey: "description") ?? "",
                    website: dict.string(forKey: "website") ?? ""
                )
            }
            DispatchQueue.main.async { breweries = list }
        }
    }
}
