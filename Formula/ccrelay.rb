class Ccrelay < Formula
  desc "Local GitHub Copilot proxy for Codex"
  homepage "https://github.com/Simo-C3/homebrew-ccrelay"
  url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.5.0/ccrelay-0.5.0.tar.gz"
  sha256 "80c0192668b8afd363bb319c313def017533b64c84c69084f8deb4883d06eead"
  license "MIT"
  head "https://github.com/Simo-C3/homebrew-ccrelay.git", branch: "main"

  bottle do
    root_url "https://github.com/Simo-C3/homebrew-ccrelay/releases/download/v0.5.0"
    sha256 arm64_sequoia: "a3206b025263363abb157bbace4470dc30e3dac6b55dd6c26c56c7bdbb41554f"
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
