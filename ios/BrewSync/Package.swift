// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BrewSync",
    platforms: [.iOS(.v16)],
    dependencies: [
        .package(url: "https://github.com/couchbase/couchbase-lite-ios.git", from: "3.2.0"),
    ],
    targets: [
        .executableTarget(
            name: "BrewSync",
            dependencies: [
                .product(name: "CouchbaseLiteSwift", package: "couchbase-lite-ios"),
            ],
            path: "BrewSync"
        ),
    ]
)
