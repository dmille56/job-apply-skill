{ lib, config, pkgs, skillPackage }:
let
  cfg = config.jobApply;
  common = import ./common.nix { inherit lib; };
  homeDir = config.home.homeDirectory;
  seedFile = if cfg.configSeedFile != null then cfg.configSeedFile else
    pkgs.writeText "job-apply-defaults.json" (builtins.toJSON (common.seed cfg homeDir));
  command = lib.escapeShellArgs ([ "${skillPackage}/bin/job-apply" ] ++ common.args cfg homeDir seedFile);
in {
  options.jobApply = common.options;
  config = lib.mkIf cfg.enable {
    assertions = common.assertions cfg;
    home.packages = [ skillPackage pkgs.poppler-utils ] ++ cfg.browserPackages;
    home.activation.jobApply = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
      if [ -n "''${DRY_RUN_CMD:-}" ]; then
        $DRY_RUN_CMD ${command}
      else
        ${command}
      fi
    '';
  };
}
