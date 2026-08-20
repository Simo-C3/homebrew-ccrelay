class Ccrelay < Formula
  desc "Local GitHub Copilot proxy for Codex"
  homepage "https://github.com/Simo-C3/homebrew-ccrelay"
  url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.4.1/ccrelay-0.4.1.tar.gz"
  sha256 "c435bc6bf6f48f7d3b5400bf0e4d74eaee05a1accdd5e7edb916d9799d38db07"
  license "MIT"
  head "https://github.com/Simo-C3/homebrew-ccrelay.git", branch: "main"

  bottle do
    root_url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.4.1"
    sha256 arm64_sequoia: "38897b4dd88d826fe52625b76eb00546841d9ef33b6bb9ed9fa89b7700605a93"
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
