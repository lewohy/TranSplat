{
  description = "transplat devcontainer environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { nixpkgs, ... }:
    let
      supportedSystems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
      toolEnvironment = system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfreePredicate = pkg:
              builtins.elem (nixpkgs.lib.getName pkg) [
                "claude-code"
              ];
          };
          # report/paper(Overleaf)와 같은 pdfLaTeX + kotex 환경
          tex = pkgs.texliveMedium.withPackages (ps: with ps; [
            collection-langkorean
            latexmk
            latexindent
            chktex
          ]);
          toolPackages = with pkgs; [
            claude-code
            curl
            ffmpeg
            fish
            git
            jq
            nanum # 논문 그림 한글 글꼴 (kotex 본문과 같은 나눔명조)
            pretendard
            tex
            tex-fmt
            tinymist
            typst
            typstyle
            tzdata.out
            uv
            zellij
          ];
        in {
          inherit pkgs toolPackages;
        };
    in {
      packages = forAllSystems (system:
        let env = toolEnvironment system;
        in {
          default = env.pkgs.buildEnv {
            name = "transplat-env";
            paths = env.toolPackages;
          };
        });
    };
}
