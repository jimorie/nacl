<img src="nacl.png" height="320px"/>

*__"The salty command line interface to your Naemon configuration."__*

# NaCl

NaCl is a command line tool for working with your [Naemon](https://www.naemon.org/) configuration files. It allows you to create flexible filters for querying your object definitions, which can then be used as a basis for updates or analysis.

## Requirements

NaCl is written in [Python](https://www.python.org/) and is (somewhat) tested to work with Python versions __3.6__, __3.7__, __3.8__ and __3.9__. Your experience with other versions may vary.

## Installation

NaCl is currently __not__ available on [PyPI](https://pypi.org/) but can be installed directly from the [Github repo](https://github.com/jimorie/nacl):

    pip install git+https://github.com/jimorie/nacl.git

(Make sure that is pip is updated if you run into problems: `pip install --upgrade pip`)

## Usage

Check out the command line help for usage information:

    nacl --help

## Examples

### Filtering

#### Find a host by its `host_name`:

    $ nacl etc/ --host confluence-dev.op5.com
    # File: etc/hosts.cfg line 499
    define host {
        use                            default-host-template
        host_name                      confluence-dev.op5.com
        address                        127.0.0.1
    }

    # Total: 1 / 1520 matching object definition(s)

#### Find all hosts with `dev.op5.com` in their `host_name`:

    $ nacl etc/ --filter 'type == "host" and "dev.op5.com" in host_name'
    # File: etc/hosts.cfg line 492
    define host {
        use                            default-host-template
        host_name                      ci-slave-el6-lvmtest.dev.op5.com
        address                        127.0.0.1
    }

    # File: etc/hosts.cfg line 499
    define host {
        use                            default-host-template
        host_name                      confluence-dev.op5.com
        address                        127.0.0.1
    }

    # File: etc/hosts.cfg line 1291
    define host {
        use                            default-host-template
        host_name                      w2008-ietest-01.dev.op5.com
        address                        127.0.0.1
    }

    # Total: 3 / 1520 matching object definition(s)

#### Find all hosts that does not have a `host_name` and also does not have a `register` value of `0`:

    $ nacl etc/ --filter 'type == "host" and not host_name and register != 0'
    # File: etc/hosts.cfg line 19
    define host {
        use                            default-host-template
        alias                          Blanktesttemplate
        hostgroups                     Inheritance
        name                           Blanktesttemplate
    }

    # Total: 1 / 1520 matching object definition(s)

#### Find all hosts that are members of the hostgroup `pollergroup`:

    $ nacl etc/ --filter 'type == "host" and has_member(hostgroups, "pollergroup")'
    # File: etc/hosts.cfg line 1146
    define host {
        use                            default-host-template
        host_name                      pollerhost1
        alias                          pollerhost1
        address                        127.0.0.1
        hostgroups                     pollergroup,thunderbirds
        contact_groups                 support-group
        stalking_options               d,u
    }

    # File: etc/hosts.cfg line 1157
    define host {
        use                            default-host-template
        host_name                      pollerhost2
        address                        127.0.0.1
        hostgroups                     pollergroup
        stalking_options               n
    }

    # Total: 2 / 1520 matching object definition(s)

### Updating

#### Add a custom variable `_FOO_BAR` to all object definitions:

    $ nacl etc/ --update '_FOO_BAR = 1'
    # File: etc/hostgroups.cfg line 9
    define hostgroup {
        hostgroup_name                 Apica WPM Responsetime
        alias                          Apica WPM Responsetime
        _FOO_BAR                       1
    }

    # File: etc/hostgroups.cfg line 15
    define hostgroup {
        hostgroup_name                 apa
        _FOO_BAR                       1
    }

    ...

    # File: etc/serviceescalations.cfg line 34
    define serviceescalation {
        host_name                      1111111111111
        service_description            All_Disk_Aix_withouthak2
        contacts                       dblando,email_test,asjoholm
        contact_groups                 nachosgroup,support-group
        first_notification             1
        last_notification              2
        notification_interval          3
        escalation_period              24x7
        escalation_options             c,r,u,w
        _FOO_BAR                       1
    }

    # Total: 1520 / 1520 matching object definition(s)

#### Set the `register` value to `0` for object definitions that match the query:

    $ nacl etc/ --filter 'type == "host" and not host_name and register != 0' --update 'register = 0'
    # File: etc/hosts.cfg line 19
    define host {
        use                            default-host-template
        alias                          Blanktesttemplate
        hostgroups                     Inheritance
        name                           Blanktesttemplate
        register                       0
    }

    # Total: 1 / 1520 matching object definition(s)

#### Change all hostgroup references from `pollergroup` to `mastergroup`:

    $ nacl etc/ --filter 'type == "host" and has_member(hostgroups, "pollergroup")' --update 'hostgroups -= "pollergroup"; hostgroups += "mastergroup"'
    # File: etc/hosts.cfg line 1146
    define host {
        use                            default-host-template
        host_name                      pollerhost1
        alias                          pollerhost1
        address                        127.0.0.1
        hostgroups                     thunderbirds,mastergroup
        contact_groups                 support-group
        stalking_options               d,u
    }

    # File: etc/hosts.cfg line 1157
    define host {
        use                            default-host-template
        host_name                      pollerhost2
        address                        127.0.0.1
        stalking_options               n
        hostgroups                     mastergroup
    }

    # Total: 2 / 1520 matching object definition(s)

### Analyzing

#### Get a breakdown of all your object types:

    $ nacl etc/ --count type
    Count: type
    ===========
    834      command
    456      service
    155      host
    36       hostgroup
    12       contact
    8        timeperiod
    6        servicegroup
    3        contactgroup
    3        servicedependency
    3        serviceescalation
    2        hostdependency
    2        hostescalation

    # Total: 1520 / 1520 matching object definition(s)

#### Find out what different values for `notification_interval` are used in your hosts, services and escalations:

    $ nacl etc/ --count notification_interval --filter 'type in ["host", "service", "hostescalation", "serviceescalation"]'
    Count: notification_interval
    ============================
    595      -
    7        0
    7        5
    4        3
    2        2
    1        1

    # Total: 616 / 1520 matching object definition(s)

## Todo

* Tests
* Documentation
* Move to ITRS repo?

## Author

Copyright [ITRS Group](https://www.itrsgroup.com/).
