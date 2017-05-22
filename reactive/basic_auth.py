import glob
import os
import os.path
import subprocess

from charms.reactive import (
    when,
    when_not,
    when_any,
    when_file_changed,
    set_state,
    remove_state
)
from charms.layer import snap

from charmhelpers.core import (
    hookenv,
    host,
    templating,
)
from charmhelpers.contrib.charmsupport import nrpe

SNAP_FILE_NAME = 'basic-auth-service_*.snap'
SNAP_SERVICES = ('snap.basic-auth-service.basic-auth-service',)
TEMPLATES_DIR = (
    '/snap/basic-auth-service/current/usr/share/basic-auth-service/templates')
ALEMBIC_TEMPLATE = 'alembic.ini'
ALEMBIC_CONFIG_PATH = '/var/snap/basic-auth-service/current/alembic.ini'
SNAP_CONFIG_TEMPLATE = 'config.yaml'
SNAP_CONFIG_PATH = '/var/snap/basic-auth-service/current/config.yaml'


APPLICATION_PORT = 8080


def charm_state(state):
    """Convenience to return a reactive state name for this charm."""
    return 'basic-auth-service.{}'.format(state)


@when_not(charm_state('installed'))
def install():
    hookenv.status_set('maintenance', 'Installing basic-auth-service snap.')
    charm_dir = os.environ['JUJU_CHARM_DIR']
    snap_path = os.path.join(charm_dir, SNAP_FILE_NAME)
    snap_file = glob.glob(snap_path)[0]
    snap._install_local(snap_file)
    set_state(charm_state('installed'))
    # db migration should be applied once the service is configured
    set_state(charm_state('db-update'))


@when(charm_state('installed'), 'website.available')
def configure_website(website):
    """Configure reverse proxy to point to our application."""
    website.configure(port=APPLICATION_PORT)


@when(charm_state('installed'), 'database.master.available')
def configure_basic_auth_service(pgsql):
    """Configure the service when the database is available."""
    hookenv.status_set('maintenance', 'Writing config.')
    # write service config
    context = {'db_dsn': pgsql.master.uri, 'app_port': APPLICATION_PORT}
    templating.render(
        SNAP_CONFIG_TEMPLATE, SNAP_CONFIG_PATH, context, perms=0o440,
        templates_dir=TEMPLATES_DIR)
    hookenv.status_set('maintenance', 'Service configuration updated.')
    # write alembic config
    context = {'sqlalchemy_url': pgsql.master.uri}
    templating.render(
        ALEMBIC_TEMPLATE, ALEMBIC_CONFIG_PATH, context, perms=0o440,
        templates_dir=TEMPLATES_DIR)
    hookenv.status_set('active', 'Configuration done.')
    set_state(charm_state('configured'))


@when('basic-auth-check.available')
def basic_auth_check_configured(basic_auth_check):
    """Configure the basic-auth-check relation."""
    basic_auth_check.configure(APPLICATION_PORT)


@when('nrpe-external-master.available')
@when_not(charm_state('nrpe-initial-config'))
def initial_nrpe_config(nagios=None):
    update_nrpe_config(nagios)
    set_state(charm_state('nrpe-initial-config'))


@when(charm_state('configured'), 'nrpe-external-master.available')
@when_any('config.changed.nagios_context',
          'config.changed.nagios_servicegroups')
def update_nrpe_config(unused=None):
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname, primary=True)

    # Add a check for the snap's systemd service
    nrpe.add_init_service_checks(nrpe_setup, SNAP_SERVICES, current_unit)
    nrpe_setup.write()


@when_not('nrpe-external-master.available')
@when(charm_state('nrpe-initial-config'))
def remove_nrpe_config(nagios=None):

    hostname = nrpe.get_nagios_hostname()
    nrpe_setup = nrpe.NRPE(hostname=hostname)

    for service in SNAP_SERVICES:
        nrpe_setup.remove_check(shortname=service)

    remove_state(charm_state('nrpe-initial-config'))


@when(charm_state('configured'), charm_state('db-update'),
      'database.master.available')
def perform_database_migrations(pgsql):
    hookenv.status_set('maintenance', 'Performing database migrations.')
    subprocess.run(
        ['/snap/bin/basic-auth-service.alembic', '-c', ALEMBIC_CONFIG_PATH,
         'upgrade', 'head'],
        stderr=subprocess.PIPE, check=True)
    # Clear the state marking for needing DB migrations.
    hookenv.status_set('maintenance', 'Database migrations applied.')
    remove_state(charm_state('db-update'))


@when_file_changed(SNAP_CONFIG_PATH)
def restart_service():
    hookenv.status_set(
        'maintenance', 'Restarting service: basic-auth-service.')
    host.service_restart('snap.basic-auth-service.basic-auth-service')
    hookenv.status_set('active', 'Service up and running.')
