class Ccrelay < Formula
  desc "Local GitHub Copilot proxy for Codex"
  homepage "https://github.com/Simo-C3/homebrew-ccrelay"
  url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.4.0/ccrelay-0.4.0.tar.gz"
  sha256 "432f28866dbed2440cbac91c16245dbd66d00c49035a88fd0f1dc2c6f4a63960"
  license "MIT"
  head "https://github.com/Simo-C3/homebrew-ccrelay.git", branch: "main"

  bottle do
    root_url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.4.0"
    sha256 arm64_sequoia: "4f9289fe8eca4661b648fade82e78f113409d2cb281af6a840d6c242038a3d6f"
  end

  depends_on "rust" => :build
  depends_on "uv" => :build
  depends_on "python@3.14"

  preserve_rpath

  def install
    libexec.install Dir["*"]
    cd libexec do
      system formula_opt_bin("uv")/"uv", "sync",
             "--frozen",
             "--no-dev",
             "--no-editable",
             "--python", formula_opt_bin("python@3.14")/"python3.14"
    end
    bin.install_symlink libexec/".venv/bin/ccrelay"
  end

  service do
    run [opt_bin/"ccrelay", "proxy"]
    keep_alive true
    process_type :background
    log_path var/"log/ccrelay.log"
    error_log_path var/"log/ccrelay.log"
  end

  test do
    assert_match "ccrelay", shell_output("#{bin}/ccrelay --version")
  end
end
