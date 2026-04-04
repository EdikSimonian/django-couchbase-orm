import AuthenticationServices
import SwiftUI

struct LoginView: View {
    @ObservedObject var auth = AuthManager.shared
    @State private var showRegister = false
    @State private var appleCoordinator = AppleSignInCoordinator()
    @State private var googleHelper = GoogleSignInHelper()

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()

            VStack(spacing: 32) {
                Spacer()

                VStack(spacing: 12) {
                    Image(systemName: "mug.fill")
                        .font(.system(size: 64))
                        .foregroundColor(Theme.accent)
                    Text("BrewSync")
                        .font(.system(size: 36, weight: .bold))
                        .foregroundColor(Theme.accentLight)
                    Text("Where Django, Couchbase, and beer\nwalk into a bucket")
                        .font(.subheadline)
                        .foregroundColor(Theme.textMuted)
                        .multilineTextAlignment(.center)
                }

                Spacer()

                // Social login buttons
                VStack(spacing: 12) {
                    // Sign in with Apple
                    Button {
                        Task { await signInWithApple() }
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "apple.logo")
                                .font(.system(size: 18))
                            Text("Sign in with Apple")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.white)
                        .foregroundColor(.black)
                        .cornerRadius(12)
                    }
                    .disabled(auth.isLoading)

                    // Sign in with Google
                    Button {
                        Task { await signInWithGoogle() }
                    } label: {
                        HStack(spacing: 8) {
                            // Google "G" using SF Symbol
                            Text("G")
                                .font(.system(size: 18, weight: .bold, design: .rounded))
                                .foregroundColor(Color(red: 0.26, green: 0.52, blue: 0.96))
                            Text("Sign in with Google")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Color.white.opacity(0.95))
                        .foregroundColor(.black.opacity(0.87))
                        .cornerRadius(12)
                    }
                    .disabled(auth.isLoading)
                }

                // Divider
                HStack {
                    Rectangle().frame(height: 1).foregroundColor(Theme.border)
                    Text("or").font(.caption).foregroundColor(Theme.textMuted)
                    Rectangle().frame(height: 1).foregroundColor(Theme.border)
                }

                // Email sign in
                Button {
                    Task { await auth.login() }
                } label: {
                    HStack {
                        if auth.isLoading {
                            ProgressView().tint(.black)
                        }
                        Text("Sign In with Email")
                            .fontWeight(.semibold)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Theme.accent)
                    .foregroundColor(.black)
                    .cornerRadius(12)
                }
                .disabled(auth.isLoading)

                Button("Create an Account") {
                    showRegister = true
                }
                .foregroundColor(Theme.accent)
                .font(.subheadline)

                if let error = auth.error {
                    Text(error)
                        .font(.caption)
                        .foregroundColor(Theme.danger)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)
                }

                Spacer().frame(height: 24)
            }
            .padding(.horizontal, 32)
        }
        .sheet(isPresented: $showRegister) {
            RegisterView()
        }
    }

    private func signInWithApple() async {
        do {
            let result = try await appleCoordinator.signIn()
            await auth.loginWithApple(idToken: result.idToken, fullName: result.fullName)
        } catch let error as AuthError where error == .cancelled {
            // User cancelled, ignore
        } catch {
            auth.error = error.localizedDescription
        }
    }

    private func signInWithGoogle() async {
        do {
            let idToken = try await googleHelper.signIn()
            await auth.loginWithGoogle(idToken: idToken)
        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            // User cancelled, ignore
        } catch {
            auth.error = error.localizedDescription
        }
    }
}

struct RegisterView: View {
    @ObservedObject var auth = AuthManager.shared
    @Environment(\.dismiss) private var dismiss

    @State private var username = ""
    @State private var email = ""
    @State private var password = ""
    @State private var error: String?
    @State private var isLoading = false

    var body: some View {
        NavigationStack {
            ZStack {
                Theme.bg.ignoresSafeArea()

                VStack(spacing: 20) {
                    TextField("Username", text: $username)
                        .textFieldStyle(BrewTextFieldStyle())
                        .autocapitalization(.none)
                        .autocorrectionDisabled()

                    TextField("Email", text: $email)
                        .textFieldStyle(BrewTextFieldStyle())
                        .keyboardType(.emailAddress)
                        .autocapitalization(.none)

                    SecureField("Password", text: $password)
                        .textFieldStyle(BrewTextFieldStyle())

                    if let error = error {
                        Text(error)
                            .font(.caption)
                            .foregroundColor(Theme.danger)
                    }

                    Button {
                        Task { await register() }
                    } label: {
                        HStack {
                            if isLoading { ProgressView().tint(.black) }
                            Text("Create Account").fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 16)
                        .background(Theme.accent)
                        .foregroundColor(.black)
                        .cornerRadius(12)
                    }
                    .disabled(isLoading || username.isEmpty || email.isEmpty || password.count < 8)

                    Spacer()
                }
                .padding(24)
            }
            .navigationTitle("Create Account")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                        .foregroundColor(Theme.accent)
                }
            }
        }
    }

    private func register() async {
        isLoading = true
        error = nil
        do {
            try await auth.register(username: username, email: email, password: password)
            dismiss()
            await auth.login()
        } catch {
            self.error = error.localizedDescription
        }
        isLoading = false
    }
}

struct BrewTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(14)
            .background(Theme.card)
            .foregroundColor(Theme.text)
            .cornerRadius(10)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Theme.border, lineWidth: 1))
    }
}
