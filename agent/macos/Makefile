# KMFlow macOS Agent — Build System
# Wraps SPM for development and adds signing/notarization/packaging targets.

SCHEME = KMFlowAgent
BUNDLE_ID = com.kmflow.agent
MIN_MACOS = 13.0

.PHONY: build test lint clean sign notarize package-dmg package-pkg resolve

# Development targets (SPM-based)

resolve:
	swift package resolve

build: resolve
	swift build

build-release: resolve
	swift build -c release

test:
	swift test

lint:
	@if command -v swiftlint >/dev/null 2>&1; then \
		swiftlint --strict; \
	else \
		echo "SwiftLint not installed. Install via: brew install swiftlint"; \
	fi

clean:
	swift package clean
	rm -rf .build DerivedData

# Production targets (require Xcode + developer certificates)

sign:
	@echo "Code signing requires Xcode and a valid Developer ID certificate."
	@echo "Run: codesign --deep --force --verify --verbose --sign 'Developer ID Application: YOUR_TEAM' .build/release/KMFlowAgent"

notarize:
	@echo "Notarization requires Xcode and Apple Developer credentials."
	@echo "1. Create ZIP: ditto -c -k --keepParent .build/release/KMFlowAgent.app KMFlowAgent.zip"
	@echo "2. Submit: xcrun notarytool submit KMFlowAgent.zip --apple-id YOUR_ID --team-id YOUR_TEAM"
	@echo "3. Staple: xcrun stapler staple .build/release/KMFlowAgent.app"

package-dmg:
	@echo "DMG packaging requires create-dmg: brew install create-dmg"
	@echo "create-dmg --volname 'KMFlow Agent' --app-drop-link 450 218 KMFlowAgent.dmg .build/release/KMFlowAgent.app"

package-pkg:
	@echo "PKG packaging for MDM deployment:"
	@echo "pkgbuild --root .build/release/KMFlowAgent.app --identifier $(BUNDLE_ID) --version 1.0.0 --install-location /Applications KMFlowAgent.pkg"
