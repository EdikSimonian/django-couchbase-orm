import SwiftUI

struct BeerListView: View {
    @StateObject private var viewModel = BeerListViewModel()
    @ObservedObject var auth = AuthManager.shared
    @State private var showAddBeer = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Custom header (replaces toolbar to avoid iOS 26 nav bar bugs)
                    HStack {
                        Image(systemName: "mug.fill")
                            .font(.title2)
                            .foregroundColor(Theme.accent)
                        Text("BrewSync")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(Theme.accentLight)
                        Spacer()
                        if auth.isAdmin {
                            Button {
                                showAddBeer = true
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
                        TextField("Search beers...", text: $viewModel.searchText)
                            .foregroundColor(Theme.text)
                    }
                    .padding(12)
                    .background(Theme.card)
                    .cornerRadius(10)
                    .padding(.horizontal)

                    // Style filter chips
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            FilterChip(title: "All", isActive: viewModel.selectedStyle.isEmpty) {
                                viewModel.selectedStyle = ""
                            }
                            ForEach(viewModel.availableStyles, id: \.self) { style in
                                FilterChip(title: style, isActive: viewModel.selectedStyle == style) {
                                    viewModel.selectedStyle = style
                                }
                            }
                        }
                        .padding(.horizontal)
                    }
                    .padding(.vertical, 8)

                    // Sort + count
                    HStack {
                        Text("\(viewModel.filteredBeers.count) beers")
                            .font(.caption)
                            .foregroundColor(Theme.textMuted)
                        Spacer()
                        Picker("Sort", selection: $viewModel.sortBy) {
                            ForEach(BeerListViewModel.SortOption.allCases, id: \.self) { opt in
                                Text(opt.rawValue).tag(opt)
                            }
                        }
                        .pickerStyle(.segmented)
                        .frame(width: 200)
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 8)

                    // Beer grid
                    ScrollView {
                        LazyVGrid(columns: [
                            GridItem(.flexible(), spacing: 12),
                            GridItem(.flexible(), spacing: 12),
                        ], spacing: 12) {
                            ForEach(viewModel.filteredBeers) { beer in
                                NavigationLink(destination: BeerDetailView(beer: beer)) {
                                    BeerCardView(beer: beer)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.horizontal)
                        .padding(.bottom, 20)
                    }
                }
            }
            .navigationBarHidden(true)
            .sheet(isPresented: $showAddBeer) {
                BeerFormView(mode: .add)
            }
            .onAppear { viewModel.startObserving() }
            .onDisappear { viewModel.stopObserving() }
        }
    }
}

struct FilterChip: View {
    let title: String
    let isActive: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.caption)
                .padding(.horizontal, 14)
                .padding(.vertical, 6)
                .background(isActive ? Theme.accent.opacity(0.2) : Color.clear)
                .foregroundColor(isActive ? Theme.accent : Theme.textMuted)
                .overlay(
                    RoundedRectangle(cornerRadius: 20)
                        .stroke(isActive ? Theme.accent : Theme.border, lineWidth: 1)
                )
                .cornerRadius(20)
        }
    }
}
