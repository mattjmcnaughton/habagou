{ pkgs, ... }:

{
  packages = with pkgs; [
    bashInteractive
    curl
    git
    just
    nodejs_22
    pnpm
    postgresql_16
    python312
    uv
  ];

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_16;
    listen_addresses = "";
    initialDatabases = [
      {
        name = "habagou";
        user = "habagou";
      }
    ];
  };

  enterShell = ''
    eval "$(${pkgs.python312}/bin/python scripts/dev_env.py env)"
  '';
}
