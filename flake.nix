{
  description = "Portable job application skill for Codex, Claude Code, OpenCode, and Pi";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f (import nixpkgs { inherit system; }));
      mkPackage = pkgs:
        let
          skill = pkgs.runCommand "job-apply-skill" { nativeBuildInputs = [ pkgs.makeWrapper ]; } ''
            mkdir -p "$out/share/job-apply"
            cp -R ${./skill-source/job-apply}/. "$out/share/job-apply/"
            chmod -R u+w "$out/share/job-apply"
            rm "$out/share/job-apply/scripts/run-helper.sh"
            makeWrapper ${pkgs.python3}/bin/python3 "$out/share/job-apply/scripts/run-helper.sh" \
              --add-flags "$out/share/job-apply/scripts/job_apply.py" \
              --prefix PATH : ${pkgs.lib.makeBinPath [ pkgs.poppler-utils ]}
          '';
          cli = pkgs.writeShellApplication {
            name = "job-apply";
            runtimeInputs = [ pkgs.python3 pkgs.poppler-utils ];
            text = ''
              exec python3 "${skill}/share/job-apply/scripts/job_apply.py" "$@"
            '';
          };
        in pkgs.symlinkJoin {
          name = "job-apply";
          paths = [ skill cli ];
          meta.mainProgram = "job-apply";
        };
    in {
      packages = forAllSystems (pkgs: let package = mkPackage pkgs; in {
        default = package;
        job-apply = package;
      });

      apps = forAllSystems (pkgs:
        let
          installer = pkgs.writeShellApplication {
            name = "install-job-apply";
            runtimeInputs = [ self.packages.${pkgs.stdenv.hostPlatform.system}.job-apply pkgs.nix pkgs.coreutils ];
            text = ''
              job-apply install "$@"
              task_state_dir="''${XDG_STATE_HOME:-$HOME/.local/state}/job-apply"
              mkdir -p "$task_state_dir"
              nix-store --add-root "$task_state_dir/nix-runtime" --indirect \
                --realise ${self.packages.${pkgs.stdenv.hostPlatform.system}.job-apply} >/dev/null
            '';
          };
          app = { type = "app"; program = "${installer}/bin/install-job-apply"; };
        in { default = app; install = app; });

      homeManagerModules.job-apply = { lib, config, pkgs, ... }:
        import ./modules/home-manager.nix {
          inherit lib config pkgs;
          skillPackage = self.packages.${pkgs.stdenv.hostPlatform.system}.job-apply;
        };

      nixosModules.job-apply = { lib, config, pkgs, ... }:
        import ./modules/nixos.nix {
          inherit lib config pkgs;
          skillPackage = self.packages.${pkgs.stdenv.hostPlatform.system}.job-apply;
        };

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [ pkgs.python3 pkgs.poppler-utils pkgs.alejandra ];
        };
      });

      checks = forAllSystems (pkgs: {
        helper = pkgs.runCommand "job-apply-check" {
          nativeBuildInputs = [ pkgs.python3 pkgs.poppler-utils ];
        } ''
          export PYTHONDONTWRITEBYTECODE=1
          python3 ${./tests/test_helper.py} ${./skill-source/job-apply}
          touch "$out"
        '';
      });

      formatter = forAllSystems (pkgs: pkgs.alejandra);
    };
}
