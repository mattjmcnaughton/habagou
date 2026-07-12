{ pkgs, ... }:

{
  env.LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";

  packages = with pkgs; [
    bashInteractive
    curl
    git
    just
    nodejs_22
    pnpm
    postgresql_16
    python312
    stdenv.cc.cc.lib
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
    # The integration and e2e suites provision throwaway template and per-test
    # databases, so the app role needs CREATEDB (the Docker Postgres used in CI
    # grants this implicitly by making the bootstrap user a superuser).
    initialScript = ''
      ALTER ROLE habagou CREATEDB;
    '';
  };

  services.keycloak = {
    enable = true;
    initialAdminPassword = "admin";
    settings = {
      http-host = "0.0.0.0";
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
