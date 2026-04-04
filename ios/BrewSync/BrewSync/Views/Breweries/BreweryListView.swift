import SwiftUI
import CouchbaseLiteSwift

@MainActor
class BreweryListViewModel: ObservableObject {
    @Published var breweries: [Brewery] = []
    @Published var searchText: String = ""
    private var queryToken: ListenerToken?

    var filteredBreweries: [Brewery] {
        if searchText.isEmpty { return breweries }
        return breweries.filter { $0.name.localizedCaseInsensitiveContains(searchText) }
    }

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
    @ObservedObject var auth = AuthManager.shared
    @State private var showAddBrewery = false
    @State private var showEditBrewery: Brewery?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Header
                    HStack {
                        Image(systemName: "building.2.fill")
                            .font(.title2)
                            .foregroundColor(Theme.accent)
                        Text("Breweries")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(Theme.accentLight)
                        Spacer()
                        if auth.isAdmin {
                            Button {
                                showAddBrewery = true
                            } label: {
                                Image(systemName: "plus.circle.fill")
                                    .font(.title3)
                                    .foregroundColor(Theme.accent)
                            }
                        }
                        Menu {
                            Text("Signed in as \(auth.username)")
                            if auth.isAdmin {
                                Label("Admin", systemImage: "shield.checkered")
                            }
                            Divider()
                            Button("Sign Out", role: .destructive) {
                                auth.logout()
                            }
                        } label: {
                            Image(systemName: "person.circle")
                                .font(.title3)
                                .foregroundColor(Theme.textMuted)
                        }
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 10)

                    // Search bar
                    HStack {
                        Image(systemName: "magnifyingglass")
                            .foregroundColor(Theme.textMuted)
                        TextField("Search breweries...", text: $viewModel.searchText)
                            .foregroundColor(Theme.text)
                    }
                    .padding(12)
                    .background(Theme.card)
                    .cornerRadius(10)
                    .padding(.horizontal)

                    // Count
                    HStack {
                        Text("\(viewModel.filteredBreweries.count) breweries")
                            .font(.caption)
                            .foregroundColor(Theme.textMuted)
                        Spacer()
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 8)

                    // Brewery grid
                    ScrollView {
                        LazyVGrid(columns: [
                            GridItem(.flexible(), spacing: 12),
                            GridItem(.flexible(), spacing: 12),
                        ], spacing: 12) {
                            ForEach(viewModel.filteredBreweries) { brewery in
                                BreweryCardView(brewery: brewery)
                                    .contextMenu {
                                        if auth.isAdmin {
                                            Button {
                                                showEditBrewery = brewery
                                            } label: {
                                                Label("Edit", systemImage: "pencil")
                                            }
                                            Button(role: .destructive) {
                                                try? DatabaseManager.shared.deleteBrewery(id: brewery.id)
                                            } label: {
                                                Label("Delete", systemImage: "trash")
                                            }
                                        }
                                    }
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 20)
                    }
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showAddBrewery) {
                BreweryFormView(mode: .add)
            }
            .sheet(item: $showEditBrewery) { brewery in
                BreweryFormView(mode: .edit(brewery))
            }
            .onAppear { viewModel.startObserving() }
            .onDisappear { viewModel.stopObserving() }
        }
    }
}

struct BreweryCardView: View {
    let brewery: Brewery

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(brewery.name)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)
                .lineLimit(2)

            if !brewery.city.isEmpty || !brewery.state.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "mappin")
                        .font(.caption2)
                    Text([brewery.city, brewery.state]
                        .filter { !$0.isEmpty }
                        .joined(separator: ", "))
                        .lineLimit(1)
                }
                .font(.caption)
                .foregroundColor(Theme.accent)
            }

            if !brewery.country.isEmpty {
                Text(brewery.country)
                    .font(.caption)
                    .foregroundColor(Theme.textMuted)
            }

            Spacer(minLength: 0)

            if !brewery.description.isEmpty {
                Text(brewery.description)
                    .font(.caption)
                    .foregroundColor(Theme.textMuted)
                    .lineLimit(2)
            }

            if !brewery.website.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "globe")
                        .font(.caption2)
                    Text("Website")
                        .font(.caption)
                }
                .foregroundColor(Theme.accent.opacity(0.7))
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.card)
        .cornerRadius(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }
}
