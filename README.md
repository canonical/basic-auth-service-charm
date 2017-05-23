# Overview

This charm deploys
the [basic-auth-service](https://github.com/CanonicalLtd/basic-auth-service),
which provides HTTP basic-authorization credentials validation and management.

# Deployment

The charm should be deployed along with
the [PostgreSQL charm](https://jujucharms.com/postgresql/), to provide the
database for credentials:

```bash
juju deploy cs:postgresql
juju add-relation basic-auth-service:database postgresql:db
```

# Credentials setup

Once the application is deployed and related to the database, credentials for
API access can be added with

```bash`
juju run --unit basic-auth-service/0 'sudo /snap/bin/basic-auth-service.manage-credentials add <user>
```

The command prints out generated credentials for the user and can be run on any
unit of the deployed application.


# `basic-auth-check` relation

The basic-auth-service can be related via `basic-auth-check` relation with
services that need Basic-Auth credentials validation. This is done by:

```bash
juju add-relation basic-auth-service:basic-auth-check <other-service>:basic-auth-check
```

The related service can use the
[`basic-auth-check` interface](https://github.com/CanonicalLtd/juju-interface-basic-auth-check) to
implement relation configuration handling.

Multiple units of this application can be deployed in order to achieve
high-availability.
