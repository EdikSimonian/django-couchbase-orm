import SwiftUI

struct BeerDetailView: View {
    @StateObject private var viewModel: BeerDetailViewModel
    @ObservedObject var auth = AuthManager.shared
    @State private var showEditForm = false
    @State private var showDeleteAlert = false
    @Environment(\.dismiss) private var dismiss

    init(beer: Beer) {
        _viewModel = StateObject(wrappedValue: BeerDetailViewModel(beer: beer))
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    // Header
                    VStack(alignment: .leading, spacing: 8) {
                        Text(viewModel.beer.name)
                            .font(.system(size: 28, weight: .bold))
                            .foregroundColor(.white)
                        if !viewModel.beer.style.isEmpty {
                            Text(viewModel.beer.style)
                                .font(.subheadline)
                                .foregroundColor(Theme.accent)
                        }
                    }

                    // Badges
                    HStack(spacing: 10) {
                        if let abv = viewModel.beer.abv {
                            BadgeView(text: String(format: "%.1f%% ABV", abv), style: .accent)
                        }
                        if let ibu = viewModel.beer.ibu {
                            BadgeView(text: "\(ibu) IBU", style: .muted)
                        }
                    }

                    // Meta cards
                    HStack(spacing: 12) {
                        MetaCard(label: "BREWERY", value: viewModel.brewery?.name ?? "Unknown") {
                            if let brewery = viewModel.brewery, !brewery.city.isEmpty {
                                Text("\(brewery.city), \(brewery.state)")
                                    .font(.caption2)
                                    .foregroundColor(Theme.textMuted)
                            }
                        }
                        MetaCard(label: "RATING", value: "") {
                            RatingStarsView(
                                rating: viewModel.beer.avgRating,
                                count: viewModel.beer.ratingCount
                            )
                        }
                    }

                    // User rating
                    if auth.isAuthenticated {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("YOUR RATING")
                                .font(.caption)
                                .foregroundColor(Theme.textMuted)
                                .tracking(1)
                            RatingStarsView(
                                rating: Double(viewModel.userRating),
                                count: 0,
                                interactive: true
                            ) { score in
                                viewModel.submitRating(score: score)
                            }
                        }
                        .padding()
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Theme.card)
                        .cornerRadius(12)
                    }

                    // Description
                    if !viewModel.beer.description.isEmpty {
                        Text(viewModel.beer.description)
                            .font(.body)
                            .foregroundColor(Theme.textMuted)
                            .lineSpacing(4)
                    }
                }
                .padding(20)
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if auth.isAdmin {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button { showEditForm = true } label: {
                            Label("Edit", systemImage: "pencil")
                        }
                        Button(role: .destructive) { showDeleteAlert = true } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    } label: {
                        Image(systemName: "ellipsis.circle")
                            .foregroundColor(Theme.accent)
                    }
                }
            }
        }
        .sheet(isPresented: $showEditForm) {
            BeerFormView(mode: .edit(viewModel.beer))
        }
        .alert("Delete Beer?", isPresented: $showDeleteAlert) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                try? viewModel.deleteBeer()
                dismiss()
            }
        } message: {
            Text("This will permanently delete \(viewModel.beer.name).")
        }
        .onAppear { viewModel.startRefreshing() }
        .onDisappear { viewModel.stopRefreshing() }
    }
}

// MARK: - Subviews

struct BadgeView: View {
    let text: String
    let style: BadgeStyle

    enum BadgeStyle { case accent, muted }

    var body: some View {
        Text(text)
            .font(.system(size: 14, weight: .semibold))
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(style == .accent ? Theme.accent : Color(hex: "333"))
            .foregroundColor(style == .accent ? .black : Theme.textMuted)
            .cornerRadius(16)
    }
}

struct MetaCard<Content: View>: View {
    let label: String
    let value: String
    @ViewBuilder let extra: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption2)
                .foregroundColor(Theme.textMuted)
                .tracking(1)
            if !value.isEmpty {
                Text(value)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(Theme.text)
            }
            extra
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(Theme.card)
        .cornerRadius(12)
    }
}
