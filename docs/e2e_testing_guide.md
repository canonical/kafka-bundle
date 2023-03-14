# E2E Testing Framework

## Tests parameterization with arguments
### Running the tests
To run tests with different configurations, you can pass arguments to the `tox -e interation-e2e -- ` command. These arguments are parsed by `tests/integration/e2e/conftest.py` as `scope=module` arguments, defaulting to what is set in `tests/integration/e2e/literals.py` if not set

Optional flags for fresh deployments are as follows:
- `--tls` for running the cluster with SSL encryption

For example: 
```bash
# normal:
tox -e integration-e2e

# with tls:
tox -e integration-e2e -- --tls
```

### Pre-existing deployments
Essential flags for running tests on a pre-existing deployment (e.g for validation) are as follows:
- `--kafka` and `--zookeeper` with values of their pre-existing Juju Application names
- `--model` with value of the pre-existing Juju model they're deployed under
- `--no-deploy` to skip deployment of a new cluster, and teardown at test completion

For example:
```bash
# normal:
tox -e integration-e2e -- --kafka=<KAFKA_APP_NAME> --zookeeper=<ZOOKEEPER_APP_NAME> --model=<JUJU_MODEL_NAME> --no-deploy

# with tls:
tox -e integration-e2e -- --tls --kafka=<KAFKA_APP_NAME> --zookeeper=<ZOOKEEPER_APP_NAME> --model=<JUJU_MODEL_NAME> --no-deploy
```
A commented out example of this is in `tox:integration-e2e-existing`, purely for demonstration purposes. Will be updated once the tests are more fleshed out.

### Why do I have to pass Kafka + ZooKeeper flags?
Pre-existing deployments might not have applications called `kafka` or `zookeeper` or `tls-certificates-operator`. By passing the name, it gets loaded as a Pytest fixture name that we can rely on during relations with, say, a `producer` client. If not set, they default to the main Charm name (except `tls-certificates-operator`, which defaults to `certificates` because the former is long). 

In order to use these, you can do something similar to the following:
```python
async def test_cluster_is_deployed_successfully(
    ops_test: OpsTest, kafka, zookeeper, tls, certificates
):
    assert ops_test.model.applications[kafka].status == "active"
    assert ops_test.model.applications[zookeeper].status == "active"

    if tls:
        assert ops_test.model.applications[certificates].status == "active"
```

## Writing tests using factory fixtures
Fixtures can be found in `tests/integration/e2e/conftest.py` for `deploy_cluster` and `deploy_client`. All `pytest` fixtures evaluate before test-start, caching the returned values to be shared across their defined `scope`. 

### Deploying the Cluster
`deploy_cluster` has `scope="module"`, and when it is first referenced in a module (e.g as a function fixture), it will run to completion, either calling a nested function `_deploy_non_tls_cluster` or `_deploy_tls_cluster` based on the passed `--tls` flag. Each of the main 3 applications (Kafka, ZooKeeper, tls-certificates-operator) will run in their own async operations to hopefully speed up deployment.

Although somewhat obscured, as the fixture doesn't need to be re-referenced, returning the coroutine to be fully executed on test-module set-up within `_deploy_X_cluster` is fine, and gives us the option of extending it if ever we want to deploy across multiple models concurrently. Unlikely however with the state of our CI.

Tests decorated with `@pytest.mark.skip_if_deployed` will not run if `--no-deploy` and `--model` have been passed.

Make sure to start your test modules with something similar to the following:
```python
@pytest.mark.skip_if_deployed
async def test_deploy(ops_test: OpsTest, deploy_cluster):
    await asyncio.sleep(0)  # do nothing, await deploy_cluster
```

### Deploying Producer/Consumer Clients
The `deploy_client` fixture has `scope="function"`, and uses a [Factory pattern](https://docs.pytest.org/en/6.2.x/fixture.html#factories-as-fixtures) to yield a coroutine which can be then awaited from within the test. This allows you to pass `role` as an argument, and pass as many instances of that client as you like.

When executed, a nested function `_deploy_client(role)` generates a UUID and names the application `role-UUID`, e.g `producer-xciv` to avoid app-name clashes Juju side. It also relates to Kafka and waits for Kafka to `active/idle`. It passes back application name (e.g `producer-xciv`) so that you can reference it from within `ops_test` for whatever actions/scaling you might want to do in the actual test.

On completion of the actual test function, all deployed clients from within the function will be `juju remove`'d as clean-up.

To use these clients in your test modules, do something similar to the following:
```python
async def test_clients_actually_set_up(ops_test: OpsTest, deploy_client):
    producer = await deploy_client(role="producer")
    consumer = await deploy_client(role="consumer")

    assert ops_test.model.applications[consumer].status == "active"
    assert ops_test.model.applications[producer].status == "active"


async def test_clients_actually_tear_down_after_test_exit(ops_test: OpsTest):
    assert "consumer" not in "".join(ops_test.model.applications.keys())
    assert "producer" not in "".join(ops_test.model.applications.keys())
```

