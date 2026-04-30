import SwiftUI
import PhotosUI
import UIKit
import UniformTypeIdentifiers

// MARK: - Camera (UIKit -> SwiftUI bridge)

/// Wraps UIImagePickerController for the camera. SwiftUI doesn't have a
/// native camera capture yet, so this is the standard glue.
struct CameraPicker: UIViewControllerRepresentable {
    @Environment(\.dismiss) private var dismiss
    let onCapture: (UIImage) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraDevice = .rear
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker
        init(parent: CameraPicker) { self.parent = parent }

        func imagePickerController(_ picker: UIImagePickerController,
                                   didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let img = info[.originalImage] as? UIImage {
                parent.onCapture(img)
            }
            parent.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            parent.dismiss()
        }
    }
}

// MARK: - Photo library (SwiftUI native PhotosPicker wrapper)

/// Convenience: load the picked PhotosPickerItem into a UIImage.
@MainActor
func loadUIImage(from item: PhotosPickerItem) async -> UIImage? {
    do {
        if let data = try await item.loadTransferable(type: Data.self),
           let img = UIImage(data: data) {
            return img
        }
    } catch {
        print("PhotosPicker load failed: \(error)")
    }
    return nil
}
