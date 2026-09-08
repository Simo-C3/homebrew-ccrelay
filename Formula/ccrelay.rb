class Ccrelay < Formula
  desc "Local GitHub Copilot proxy for Codex"
  homepage "https://github.com/Simo-C3/homebrew-ccrelay"
  url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.5.1/ccrelay-0.5.1.tar.gz"
  sha256 "160a64975196ce2451b1a0983bcb893f8376dc6584e7abc8bb5b61022eb903fd"
  license "MIT"
  head "https://github.com/Simo-C3/homebrew-ccrelay.git", branch: "main"

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
