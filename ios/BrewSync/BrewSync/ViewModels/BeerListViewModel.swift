import Foundation
import CouchbaseLiteSwift

/// Observes the beers collection via Live Query and provides filtered/sorted beer lists.
@MainActor
class BeerListViewModel: ObservableObject {
    @Published var beers: [Beer] = []
    @Published var searchText: String = ""
    @Published var selectedStyle: String = ""
    @Published var sortBy: SortOption = .name

    private var liveQuery: Query?
    private var queryToken: ListenerToken?

    enum SortOption: String, CaseIterable {
        case name = "Name"
        case abv = "ABV"
        case rating = "Rating"
    }

    var filteredBeers: [Beer] {
        var result = beers
        if !searchText.isEmpty {
            result = result.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
        }
        if !selectedStyle.isEmpty {
            result = result.filter { $0.style == selectedStyle }
        }
        switch sortBy {
        case .name: result.sort { $0.name < $1.name }
        case .abv: result.sort { ($0.abv ?? 0) > ($1.abv ?? 0) }
        case .rating: result.sort { $0.avgRating > $1.avgRating }
        }
        return result
    }

    var availableStyles: [String] {
        Array(Set(beers.compactMap { $0.style.isEmpty ? nil : $0.style })).sorted()
    }

    func startObserving() {
        guard let collection = DatabaseManager.shared.beerCollection else { return }

        let query = QueryBuilder
            .select(SelectResult.all(), SelectResult.expression(Meta.id))
            .from(DataSource.collection(collection))

        queryToken = query.addChangeListener { [weak self] change in
            guard let results = change.results else { return }
            let beers = results.compactMap { result -> Beer? in
                guard let dict = result.dictionary(at: 0) else { return nil }
                let docId = result.string(at: 1) ?? ""
                return Beer(
                    id: Int(docId) ?? 0,
                    name: dict.string(forKey: "name") ?? "",
                    abv: dict.contains(key: "abv") ? dict.double(forKey: "abv") : nil,
                    ibu: dict.contains(key: "ibu") ? dict.int(forKey: "ibu") : nil,
                    style: dict.string(forKey: "style") ?? "",
                    breweryId: dict.contains(key: "brewery_id") ? dict.int(forKey: "brewery_id") : nil,
                    description: dict.string(forKey: "description") ?? "",
                    imageUrl: dict.string(forKey: "image_url") ?? "",
                    avgRating: dict.double(forKey: "avg_rating"),
                    ratingCount: dict.int(forKey: "rating_count"),
                    createdAt: dict.string(forKey: "created_at"),
                    updatedAt: dict.string(forKey: "updated_at")
                )
            }
            DispatchQueue.main.async {
                self?.beers = beers
            }
        }

        liveQuery = query
    }

    func stopObserving() {
        if let token = queryToken {
            liveQuery?.removeChangeListener(withToken: token)
            queryToken = nil
        }
    }
}
