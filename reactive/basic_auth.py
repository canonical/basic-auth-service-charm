import glob
import os
import os.path
import subprocess
import yaml

from charms import reactive
import charms.layer.snap

from charmhelpers.core import (
    hookenv,
    host,
    templating,
)
from charmhelpers.contrib.charmsupport import nrpe

SNAP_FILE_NAME = "basic-auth-service_*.snap"
SNAP_CONFIG_PATH = "/var/snap/basic-auth-service/current/config.yaml"
SNAP_SERVICES = ("snap.basic-auth-service.basic-auth-service",)
ALEMBIC_TEMPLATE = "templates/alembic.ini"
ALEMBIC_CONFIG_PATH = "/var/snap/basic-auth-service/current/alembic.ini"

PORT = 8080


def charm_state(state):
    """Convenience to return a reactive state name for this charm."""
    return 'basic-auth-service.{}'.format(state)


@reactive.hook("install")
def install_snap():
    hookenv.status_set("maintenance", "Installing basic-auth-service snap.")
    charm_dir = os.environ["JUJU_CHARM_DIR"]
    snap_path = os.path.join(charm_dir, SNAP_FILE_NAME)
    snap_file = glob.glob(snap_path)[0]
    charms.layer.snap._install_local(snap_file)
    reactive.set_state(charm_state("installed"))
    reactive.set_state(charm_state("db-update"))
    reactive.remove_state(charm_state("configured"))


@reactive.when("website.available")
def configure_website(website):
    """Configure reverse proxy to point to our application."""
    website.configure(port=PORT)


@reactive.when("database.master.available", charm_state("installed"))
def configure_basic_auth_service(pgsql):
    """Configure the service when the database is available."""
    hookenv.status_set("maintenance", "Writing config.")
    snap_config = {
        "database": {
            "dsn": pgsql.master.uri,
        }}
    with open(SNAP_CONFIG_PATH, "w") as config_file:
        yaml.dump(snap_config, stream=config_file)
    hookenv.status_set("maintenance", "Service configuration updated.")

    charm_dir = os.environ["JUJU_CHARM_DIR"]
    context = {"sqlalchemy_postgres_uri": pgsql.master.uri}
    templating.render(
        ALEMBIC_TEMPLATE, ALEMBIC_CONFIG_PATH, context, perms=0o440,
        templates_dir=charm_dir)
    reactive.set_state(charm_state("configured"))
    hookenv.status_set("active", "Configuration done.")


@reactive.when('nrpe-external-master.available')
@reactive.when_not('nrpe-external-master.initial-config')
def initial_nrpe_config(nagios=None):
    reactive.set_state('nrpe-external-master.initial-config')
    update_nrpe_config(nagios)


@reactive.when(charm_state("installed"),
               charm_state("configured"),
               "nrpe-external-master.available")
@reactive.when_any('config.changed.nagios_context',
                   'config.changed.nagios_servicegroups')
def update_nrpe_config(unused=None):

    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname, primary=True)

    # Add a check for the snap's systemd service
    nrpe.add_init_service_checks(nrpe_setup, SNAP_SERVICES, current_unit)
    nrpe_setup.write()


@reactive.when_not('nrpe-external-master.available')
@reactive.when('nrpe-external-master.initial-config')
def remove_nrpe_config(nagios=None):
    reactive.remove_state('nrpe-external-master.initial-config')

    hostname = nrpe.get_nagios_hostname()
    nrpe_setup = nrpe.NRPE(hostname=hostname)

    for service in SNAP_SERVICES:
        nrpe_setup.remove_check(shortname=service)


@reactive.when("database.master.available",
               charm_state("db-update"),
               charm_state("configured"))
def perform_database_migrations(pgsql):
    hookenv.status_set("maintenance", "Performing database migrations.")
    subprocess.run(
        ["/snap/bin/basic-auth-service.alembic", "-c", ALEMBIC_CONFIG_PATH,
         "upgrade", "head"],
        stderr=subprocess.PIPE, check=True)
    # Clear the state marking for needing DB migrations.
    reactive.remove_state(charm_state("db-update"))
    hookenv.status_set("maintenance", "Database migrations applied.")


@reactive.when_file_changed(SNAP_CONFIG_PATH)
def restart_service():
    """Perform a service restart."""
    hookenv.status_set(
        "maintenance", "Restarting service: basic-auth-service.")
    host.service_restart("snap.basic-auth-service.basic-auth-service")
    hookenv.status_set("active", "Service up and running.")
