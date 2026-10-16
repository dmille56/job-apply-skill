{ lib }:
{
  options = {
    enable = lib.mkEnableOption "the job-apply skill";
    installDirs = lib.mkOption {
      type = lib.types.nullOr (lib.types.listOf lib.types.str);
      default = null;
      description = "Skill destinations; null installs into the target home's .agents/skills/job-apply and .claude/skills/job-apply.";
    };
    configPath = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Writable configuration file; defaults to the target home's .config/job-apply/config.json.";
    };
    resumePath = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Initial resume filename as a string, not a Nix path; used only when configuration is absent.";
    };
    browser = lib.mkOption {
      type = lib.types.enum [ "auto" "vessel" "terminal" ];
      default = "auto";
      description = "Initial browser choice.";
    };
    submissionMode = lib.mkOption {
      type = lib.types.enum [ "review" "auto" ];
      default = "review";
      description = "Initial submission policy.";
    };
    historyPath = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Initial writable history filename; defaults to the target home's .local/state/job-apply/history.json.";
    };
    configSeedFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Absolute external JSON filename read at activation only if config is absent. Pass a string to avoid copying private contents to the Nix store. Overrides other seed settings.";
    };
    browserPackages = lib.mkOption {
      type = lib.types.listOf lib.types.package;
      default = [];
      description = "Optional existing Vessel or terminal-browser packages to install; MCP configuration remains manual.";
    };
  };

  # Only non-secret defaults are serialized. External seed contents are never read by Nix.
  seed = cfg: homeDir: {
    version = 1;
    resume_path = cfg.resumePath;
    browser = cfg.browser;
    submission_mode = cfg.submissionMode;
    history_path = if cfg.historyPath != null then cfg.historyPath else "${homeDir}/.local/state/job-apply/history.json";
    profile = {};
    answers = [];
  };

  args = cfg: homeDir: seedFile:
    [ "--config" (if cfg.configPath != null then cfg.configPath else "${homeDir}/.config/job-apply/config.json")
      "install" "--home" homeDir "--seed" seedFile ]
    ++ lib.concatMap (dir: [ "--skill-dir" dir ])
      (if cfg.installDirs != null then cfg.installDirs else [
        "${homeDir}/.agents/skills/job-apply"
        "${homeDir}/.claude/skills/job-apply"
      ]);

  assertions = cfg: [
    {
      assertion = cfg.installDirs == null || (cfg.installDirs != [] && lib.all (s: lib.hasPrefix "/" s) cfg.installDirs);
      message = "jobApply.installDirs must be a nonempty list of absolute paths, or null.";
    }
    {
      assertion = lib.all (s: s == null || lib.hasPrefix "/" s) [ cfg.configPath cfg.configSeedFile cfg.resumePath cfg.historyPath ];
      message = "jobApply path options must be absolute filenames passed as strings, or null.";
    }
  ];
}
