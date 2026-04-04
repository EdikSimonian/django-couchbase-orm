import SwiftUI
import CouchbaseLiteSwift

@MainActor
class BlogViewModel: ObservableObject {
    @Published var posts: [BlogPost] = []
    private var queryToken: ListenerToken?

    func refresh() {
        posts = DatabaseManager.shared.getAllBlogPosts()
    }

    func startObserving() {
        // Load immediately
        refresh()

        guard queryToken == nil,
              let collection = DatabaseManager.shared.blogPageCollection else { return }

        // Also select title so the query detects when title field is added/changed
        let query = QueryBuilder
            .select(
                SelectResult.expression(Meta.id),
                SelectResult.property("blog_title"),
                SelectResult.property("date"),
                SelectResult.property("intro"),
                SelectResult.property("page_ptr_id")
            )
            .from(DataSource.collection(collection))

        queryToken = query.addChangeListener { [weak self] _ in
            let posts = DatabaseManager.shared.getAllBlogPosts()
            DispatchQueue.main.async { self?.posts = posts }
        }
    }

    func stopObserving() {
        queryToken?.remove()
        queryToken = nil
    }
}

struct BlogView: View {
    @StateObject private var viewModel = BlogViewModel()
    @ObservedObject var auth = AuthManager.shared
    @State private var selectedPost: BlogPost?

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                VStack(spacing: 0) {
                    // Header
                    HStack {
                        Image(systemName: "doc.richtext")
                            .font(.title2)
                            .foregroundColor(Theme.accent)
                        Text("Blog")
                            .font(.system(size: 20, weight: .bold))
                            .foregroundColor(Theme.accentLight)
                        Spacer()
                        Text("\(viewModel.posts.count) posts")
                            .font(.caption)
                            .foregroundColor(Theme.textMuted)
                        UserMenuView()
                    }
                    .padding(.horizontal)
                    .padding(.vertical, 10)

                    if viewModel.posts.isEmpty {
                        Spacer()
                        VStack(spacing: 12) {
                            ProgressView()
                                .tint(Theme.accent)
                            Text("Syncing blog posts...")
                                .font(.caption)
                                .foregroundColor(Theme.textMuted)
                        }
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(viewModel.posts) { post in
                                    Button {
                                        selectedPost = post
                                    } label: {
                                        BlogCardView(post: post)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            .padding(.horizontal)
                            .padding(.bottom, 20)
                        }
                    }
                }
            }
            .navigationBarHidden(true)
            .sheet(item: $selectedPost) { post in
                BlogDetailView(post: post)
            }
            .onAppear {
                viewModel.startObserving()
                viewModel.refresh()
            }
            .onDisappear { viewModel.stopObserving() }
        }
    }
}

struct BlogCardView: View {
    let post: BlogPost

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(post.title)
                .font(.system(size: 16, weight: .semibold))
                .foregroundColor(.white)
                .multilineTextAlignment(.leading)

            if !post.date.isEmpty {
                Text(post.date)
                    .font(.caption)
                    .foregroundColor(Theme.accent)
            }

            if !post.intro.isEmpty {
                Text(post.intro)
                    .font(.caption)
                    .foregroundColor(Theme.textMuted)
                    .lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Theme.card)
        .cornerRadius(12)
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Theme.border, lineWidth: 1))
    }
}

struct BlogDetailView: View {
    let post: BlogPost
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        Text(post.title)
                            .font(.system(size: 24, weight: .bold))
                            .foregroundColor(.white)

                        if !post.date.isEmpty {
                            Text(post.date)
                                .font(.subheadline)
                                .foregroundColor(Theme.accent)
                        }

                        if !post.intro.isEmpty {
                            Text(post.intro)
                                .font(.body)
                                .foregroundColor(Theme.text)
                                .italic()
                        }

                        // Strip HTML tags for clean display
                        Text(post.body.strippingHTML())
                            .font(.body)
                            .foregroundColor(Theme.textMuted)
                            .lineSpacing(6)
                    }
                    .padding(20)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                        .foregroundColor(Theme.accent)
                }
            }
        }
    }
}

extension BlogPost: Hashable {
    static func == (lhs: BlogPost, rhs: BlogPost) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

extension String {
    func strippingHTML() -> String {
        replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)
            .replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&#x27;", with: "'")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
