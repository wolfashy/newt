import SwiftUI

/// Cinematic white splash. The tree drifts in slowly with a subtle scale,
/// then "N E W T" letters land one by one, deliberately. Held for a beat
/// at the end before transitioning.
struct SplashView: View {
    @State private var logoOpacity: Double = 0
    @State private var logoScale: CGFloat = 0.92

    @State private var nOpacity: Double = 0
    @State private var eOpacity: Double = 0
    @State private var wOpacity: Double = 0
    @State private var tOpacity: Double = 0

    /// Once visible, the tree very slowly breathes, alive but ambient.
    @State private var breathing: Bool = false

    var body: some View {
        ZStack {
            Color.white.ignoresSafeArea()

            VStack(spacing: 28) {
                Spacer()

                Image("NewtLogo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 300, height: 300)
                    .scaleEffect(logoScale * (breathing ? 1.015 : 1.0))
                    .opacity(logoOpacity)

                HStack(spacing: 22) {
                    Text("N").opacity(nOpacity)
                    Text("E").opacity(eOpacity)
                    Text("W").opacity(wOpacity)
                    Text("T").opacity(tOpacity)
                }
                .font(.system(size: 38, weight: .bold, design: .rounded))
                .foregroundStyle(
                    LinearGradient(
                        colors: [Theme.accentDeep, Theme.accent],
                        startPoint: .leading, endPoint: .trailing
                    )
                )
                .tracking(2)

                Spacer()
                Spacer()
            }
        }
        .onAppear {
            // Tree drifts in slowly with a breath of scale
            withAnimation(.easeOut(duration: 1.4)) {
                logoOpacity = 1.0
                logoScale = 1.0
            }
            // Once visible, gentle continuous breathing
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) {
                withAnimation(.easeInOut(duration: 4.0).repeatForever(autoreverses: true)) {
                    breathing = true
                }
            }
            // Letters land one at a time, with weight
            withAnimation(.easeOut(duration: 0.6).delay(1.05)) { nOpacity = 1.0 }
            withAnimation(.easeOut(duration: 0.6).delay(1.45)) { eOpacity = 1.0 }
            withAnimation(.easeOut(duration: 0.6).delay(1.85)) { wOpacity = 1.0 }
            withAnimation(.easeOut(duration: 0.6).delay(2.25)) { tOpacity = 1.0 }
        }
    }
}

#Preview {
    SplashView()
}
