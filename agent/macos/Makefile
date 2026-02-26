# KMFlow macOS Agent — Build System
# Wraps SPM for development and adds signing/notarization/packaging targets.

SCHEME = KMFlowAgent
BUNDLE_ID = com.kmflow.agent
MIN_MACOS = 13.0
VERSION ?= $(shell date +%Y.%m.%j)
BUILD_DIR ?= ./build
APP_NAME = KMFlow Agent
APP_BUNDLE = $(BUILD_DIR)/$(APP_NAME).app
IDENTITY ?= $(or $(KMFLOW_CODESIGN_IDENTITY),-)
SCRIPTS_DIR = scripts

.PHONY: build test lint clean sign notarize verify package-dmg package-pkg resolve \
        app-bundle release

# ──────────────────────────────────────────────────────
# Development targets (SPM-based)
# ──────────────────────────────────────────────────────

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
	rm -rf .build DerivedData $(BUILD_DIR)

# ──────────────────────────────────────────────────────
# App bundle (M1: compile + embed Python + vendor deps)
# ──────────────────────────────────────────────────────

app-bundle:
	@echo "==> Building app bundle..."
	KMFLOW_CODESIGN_IDENTITY="$(IDENTITY)" \
		bash $(SCRIPTS_DIR)/build-app-bundle.sh --output "$(BUILD_DIR)"

# ──────────────────────────────────────────────────────
# Code signing (M2)
# ──────────────────────────────────────────────────────

sign: app-bundle
	@echo "==> Signing app bundle..."
	KMFLOW_CODESIGN_IDENTITY="$(IDENTITY)" \
		bash $(SCRIPTS_DIR)/sign-all.sh "$(APP_BUNDLE)"

# ──────────────────────────────────────────────────────
# Notarization (M2)
# ──────────────────────────────────────────────────────

notarize: sign
	@echo "==> Notarizing app bundle..."
	bash $(SCRIPTS_DIR)/notarize.sh "$(APP_BUNDLE)"

# ──────────────────────────────────────────────────────
# Verification (M2)
# ──────────────────────────────────────────────────────

verify:
	@echo "==> Verifying code signing..."
	bash $(SCRIPTS_DIR)/verify-signing.sh "$(APP_BUNDLE)"

# ──────────────────────────────────────────────────────
# DMG packaging (M5)
# ──────────────────────────────────────────────────────

package-dmg: sign
	@echo "==> Building DMG installer..."
	KMFLOW_CODESIGN_IDENTITY="$(IDENTITY)" VERSION="$(VERSION)" \
		bash installer/dmg/build-dmg.sh "$(APP_BUNDLE)" "$(BUILD_DIR)"

# ──────────────────────────────────────────────────────
# PKG packaging (M6)
# ──────────────────────────────────────────────────────

package-pkg: sign
	@echo "==> Building PKG installer..."
	KMFLOW_CODESIGN_IDENTITY="$(IDENTITY)" VERSION="$(VERSION)" \
		bash installer/pkg/build-pkg.sh "$(APP_BUNDLE)" "$(BUILD_DIR)"

# ──────────────────────────────────────────────────────
# Full release (M9: build → sign → notarize → package)
# ──────────────────────────────────────────────────────

release:
	@echo "==> Full release build..."
	bash $(SCRIPTS_DIR)/release.sh
