import SwiftUI

/// Shows the animated SplashView for ~1.6s, then crossfades + scales into
/// the main ContentView. Lives between @main and ContentView so the splash
/// only runs at cold launch.
struct RootView: View {
    @State private var showSplash: Bool = true
    @State private var contentScale: CGFloat = 0.96
    @State private var contentOpacity: Double = 0

    /// Total time the splash is visible (animations run within this window).
    private let splashDuration: Double = 3.6

    var body: some View {
        ZStack {
            // Always-on chat view, animated in beneath the splash
            ContentView()
                .scaleEffect(contentScale)
                .opacity(contentOpacity)
                .allowsHitTesting(!showSplash)

            // Splash on top until the timer fires
            if showSplash {
                SplashView()
                    .transition(.opacity)
                    .zIndex(1)
            }
        }
        .onAppear {
            // Begin showing the chat just before the splash fades, so the
            // crossfade looks like Newt "settling in" rather than swapping.
            DispatchQueue.main.asyncAfter(deadline: .now() + splashDuration - 0.35) {
                withAnimation(.easeOut(duration: 0.55)) {
                    contentScale = 1.0
                    contentOpacity = 1.0
                }
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + splashDuration) {
                withAnimation(.easeInOut(duration: 0.45)) {
                    showSplash = false
                }
            }
        }
    }
}

#Preview {
    RootView()
}
