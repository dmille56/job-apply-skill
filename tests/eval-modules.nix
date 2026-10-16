{ nixpkgs, homeManager ? null }:
let
  flake = import ../flake.nix;
  outputs = flake.outputs {
    self = outputs;
    nixpkgs = { outPath = nixpkgs; lib = import (nixpkgs + "/lib"); };
  };
  pkgs = import nixpkgs { system = "x86_64-linux"; };
  nixos = import (nixpkgs + "/nixos/lib/eval-config.nix") {
    system = "x86_64-linux";
    modules = [
      outputs.nixosModules.job-apply
      {
        system.stateVersion = "25.11";
        users.users.candidate = { isNormalUser = true; home = "/home/candidate"; };
        jobApply = {
          enable = true;
          user = "candidate";
          resumePath = "/home/candidate/Documents/resume with spaces.pdf";
          configSeedFile = "/private/not-present-at-evaluation.json";
        };
      }
    ];
  };
  hm = if homeManager == null then null else import (homeManager + "/modules") {
    inherit pkgs;
    configuration = {
      imports = [ outputs.homeManagerModules.job-apply ];
      home = { username = "candidate"; homeDirectory = "/home/candidate"; stateVersion = "25.11"; };
      jobApply = { enable = true; resumePath = "/home/candidate/Documents/resume.pdf"; };
    };
  };
in {
  packages = builtins.mapAttrs (_: value: value.default.name) outputs.packages;
  nixos = {
    enabled = nixos.config.jobApply.enable;
    user = nixos.config.jobApply.user;
    validPaths = builtins.all (a: a.assertion) ((import ../modules/common.nix { inherit (pkgs) lib; }).assertions nixos.config.jobApply);
    activationDependencies = nixos.config.system.activationScripts.jobApply.deps;
    packages = map (p: p.name) nixos.config.environment.systemPackages;
  };
  homeManager = if hm == null then null else {
    enabled = hm.config.jobApply.enable;
    packages = map (p: p.name) hm.config.home.packages;
    activation = hm.config.home.activation.jobApply.data;
  };
}
