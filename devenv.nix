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

  services.keycloak = {
    enable = true;
    initialAdminPassword = "admin";
    settings = {
      http-host = "127.0.0.1";
      http-port = 12345;
      hostname = "127.0.0.1";
      hostname-strict = false;
      hostname-strict-https = false;
    };
    realms.habagou = {
      import = true;
      path = ".devenv/state/keycloak/habagou-realm.json";
    };
  };

  enterShell = ''
    eval "$(${pkgs.python312}/bin/python scripts/dev_env.py env)"
    ${pkgs.python312}/bin/python scripts/dev_env.py render-keycloak-realm >/dev/null
  '';
}
