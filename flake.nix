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
          toolPackages = with pkgs; [
            claude-code
            curl
            ffmpeg
            fish
            git
            jq
            pretendard
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
