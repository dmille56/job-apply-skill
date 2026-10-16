{ lib, config, pkgs, skillPackage }:
let
  cfg = config.jobApply;
  common = import ./common.nix { inherit lib; };
  targetUser = lib.attrByPath [ cfg.user ] {} config.users.users;
  homeDir = if cfg.homeDirectory != null then cfg.homeDirectory else targetUser.home or "/var/empty";
  seedFile = if cfg.configSeedFile != null then cfg.configSeedFile else
    pkgs.writeText "job-apply-defaults.json" (builtins.toJSON (common.seed cfg homeDir));
  command = lib.escapeShellArgs ([ "${skillPackage}/bin/job-apply" ] ++ common.args cfg homeDir seedFile);
in {
  options.jobApply = common.options // {
    user = lib.mkOption {
      type = lib.types.str;
      default = "";
      description = "Existing NixOS user receiving the skill and owning its writable configuration.";
    };
    homeDirectory = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Override the target user's installation home.";
    };
  };
  config = lib.mkIf cfg.enable {
    assertions = common.assertions cfg ++ [
      {
        assertion = cfg.user != "" && builtins.hasAttr cfg.user config.users.users;
        message = "jobApply.user must name a configured NixOS user.";
      }
      {
        assertion = lib.hasPrefix "/" homeDir;
        message = "jobApply.homeDirectory must be absolute.";
      }
    ];
    environment.systemPackages = [ skillPackage pkgs.poppler-utils ] ++ cfg.browserPackages;
    system.activationScripts.jobApply = {
      deps = [ "users" ];
      text = ''
        ${pkgs.util-linux}/bin/runuser -u ${lib.escapeShellArg cfg.user} -- ${command}
      '';
    };
  };
}
