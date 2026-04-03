import SwiftUI

/// Admin form for adding or editing a beer.
struct BeerFormView: View {
    enum Mode {
        case add
        case edit(Beer)
    }

    let mode: Mode
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var style = "IPA"
    @State private var abvText = ""
    @State private var ibuText = ""
    @State private var breweryId: Int? = nil
    @State private var description = ""
    @State private var error: String?

    @State private var breweries: [Brewery] = []

    var isEditing: Bool {
        if case .edit = mode { return true }
        return false
    }

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                ScrollView {
                    VStack(spacing: 16) {
                        Group {
                            TextField("Beer Name", text: $name)
                                .textFieldStyle(BrewTextFieldStyle())

                            Picker("Style", selection: $style) {
                                ForEach(Beer.styleChoices, id: \.self) { s in
                                    Text(s).tag(s)
                                }
                            }
                            .pickerStyle(.menu)
                            .padding(14)
                            .background(Theme.card)
                            .cornerRadius(10)
                            .foregroundColor(Theme.text)

                            HStack(spacing: 12) {
                                TextField("ABV %", text: $abvText)
                                    .textFieldStyle(BrewTextFieldStyle())
                                    .keyboardType(.decimalPad)
                                TextField("IBU", text: $ibuText)
                                    .textFieldStyle(BrewTextFieldStyle())
                                    .keyboardType(.numberPad)
                            }

                            Picker("Brewery", selection: $breweryId) {
                                Text("None").tag(nil as Int?)
                                ForEach(breweries) { b in
                                    Text(b.name).tag(b.id as Int?)
                                }
                            }
                            .pickerStyle(.menu)
                            .padding(14)
                            .background(Theme.card)
                            .cornerRadius(10)
                            .foregroundColor(Theme.text)

                            TextField("Description", text: $description, axis: .vertical)
                                .textFieldStyle(BrewTextFieldStyle())
                                .lineLimit(3...6)
                        }

                        if let error = error {
                            Text(error)
                                .font(.caption)
                                .foregroundColor(Theme.danger)
                        }

                        Button {
                            save()
                        } label: {
                            Text(isEditing ? "Save Changes" : "Add Beer")
                                .fontWeight(.semibold)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                                .background(name.isEmpty ? Theme.border : Theme.accent)
                                .foregroundColor(name.isEmpty ? Theme.textMuted : .black)
                                .cornerRadius(12)
                        }
                        .disabled(name.isEmpty)
                    }
                    .padding(20)
                }
            }
            .navigationTitle(isEditing ? "Edit Beer" : "Add Beer")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(Theme.accent)
                }
            }
            .onAppear {
                breweries = DatabaseManager.shared.getAllBreweries()
                if case .edit(let beer) = mode {
                    name = beer.name
                    style = beer.style.isEmpty ? "IPA" : beer.style
                    abvText = beer.abv.map { String(format: "%.1f", $0) } ?? ""
                    ibuText = beer.ibu.map { String($0) } ?? ""
                    breweryId = beer.breweryId
                    description = beer.description
                }
            }
        }
    }

    private func save() {
        var beer: Beer
        if case .edit(let existing) = mode {
            beer = existing
        } else {
            // Generate a temporary ID — will be replaced by server on sync
            let tempId = Int(Date().timeIntervalSince1970)
            beer = Beer(
                id: tempId,
                name: "",
                style: "",
                description: "",
                imageUrl: "",
                avgRating: 0,
                ratingCount: 0
            )
        }

        beer.name = name
        beer.style = style
        beer.abv = Double(abvText)
        beer.ibu = Int(ibuText)
        beer.breweryId = breweryId
        beer.description = description

        do {
            try DatabaseManager.shared.saveBeer(beer)
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
