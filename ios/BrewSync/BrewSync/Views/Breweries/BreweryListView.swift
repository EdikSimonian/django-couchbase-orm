import SwiftUI
import CouchbaseLiteSwift

@MainActor
class BreweryListViewModel: ObservableObject {
    @Published var breweries: [Brewery] = []
    private var queryToken: ListenerToken?

    func startObserving() {
        guard queryToken == nil,
              let collection = DatabaseManager.shared.breweryCollection else { return }

        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(collection))
            .orderBy(Ordering.property("name").ascending())

        queryToken = query.addChangeListener { [weak self] change in
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
            DispatchQueue.main.async { self?.breweries = list }
        }
    }

    func stopObserving() {
        queryToken?.remove()
        queryToken = nil
    }
}

struct BreweryListView: View {
    @StateObject private var viewModel = BreweryListViewModel()

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            if viewModel.breweries.isEmpty {
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
                        ForEach(viewModel.breweries) { brewery in
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
        .onAppear { viewModel.startObserving() }
        .onDisappear { viewModel.stopObserving() }
    }
}
