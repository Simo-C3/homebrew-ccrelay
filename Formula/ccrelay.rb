class Ccrelay < Formula
  desc "Local GitHub Copilot proxy for Codex"
  homepage "https://github.com/Simo-C3/homebrew-ccrelay"
  url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.1.0/ccrelay-0.1.0.tar.gz"
  sha256 "013b2d45d318362f0494b1ad570437ecd9ec3d221bb09ebbab09c2767291fac9"
  license "MIT"
  head "https://github.com/Simo-C3/homebrew-ccrelay.git", branch: "main"

  bottle do
    root_url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.1.0"
    rebuild 1
    sha256 arm64_sequoia: "4970c6ca7c0e8ffb560ea483aa7f4ddef067980bb466fb59cfd2564a4cddad2a"
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
    assert_match "ccrelay", shell_output("#{bin}/ccrelay version")
  end
end
