import SwiftUI
import WebKit

struct BlogView: View {
    var body: some View {
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
                }
                .padding(.horizontal)
                .padding(.vertical, 10)

                BlogWebView(url: URL(string: "https://django-couchbase-orm-production.up.railway.app/blog/")!)
            }
        }
    }
}

struct BlogWebView: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = UIColor(Theme.bg)
        webView.scrollView.backgroundColor = UIColor(Theme.bg)
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}
}
