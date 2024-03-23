"""pytest config for dockerspawner tests"""
from textwrap import indent
from unittest.mock import Mock, patch
from .utils import fixture_content

import pytest

from jupyterhub.tests.mocking import MockHub

from traitlets.config import Config

from jupyterhub_nomad_spawner.job_factory import JobData, create_job
from jupyterhub_nomad_spawner.spawner import NomadSpawner


@pytest.fixture
def hub() -> MockHub:
    hub = MockHub()
    hub.public_host = "127.0.0.1"
    hub.base_url = "/"
    hub.api_url = "api.test"

    return hub


class MockUser(Mock):
    hub: MockHub
    name = "myname"

    def __init__(self, **kwargs):
        super().__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)

    @property
    def escaped_name(self):
        return self.name

    @property
    def url(self):
        return "/server/name/lab"


@pytest.fixture
def user(hub):
    return MockUser(hub=hub)


@pytest.fixture
def config():
    cfg = Config()
    cfg.NomadSpawner.base_job_name = "jupyter-notebook"
    cfg.NomadSpawner.service_provider = "consul"

    # slim down env vars to avoid test pollution by the host config
    cfg.NomadSpawner.env_keep = [
        "LANG",
        "LC_ALL",
        "JUPYTERHUB_SINGLEUSER_APP",
    ]
    return cfg


def test_spawner_auto_remove_default(user):
    cfg = Config()
    cfg.NomadSpawner.auto_remove_jobs = False

    spawner = NomadSpawner(user=user, config=cfg)

    assert spawner.auto_remove_jobs == False


@pytest.mark.parametrize("config", [True, False])
def test_spawner_auto_remove_set(user, config):
    cfg = Config()
    cfg.NomadSpawner.auto_remove_jobs = config

    spawner = NomadSpawner(user=user, config=cfg)

    assert spawner.auto_remove_jobs == config


# @patch("jupyterhub_nomad_spawner.spawner.NomadSpawner.get_env",**{'method.return_value': {}})
@pytest.mark.asyncio
async def test_job_factory_default(user, hub, config):
    spawner = NomadSpawner(user=user, hub=hub, config=config)

    user_options = {
        "datacenters": ["dc1", "dc2"],
        "image": "jupyter/minimal-notebook",
        "memory": 512,
    }
    spawner.user_options = user_options

    # is generated in the spawners start method
    spawner.notebook_id = "123"

    nomad_service = Mock()
    job = await spawner.job_factory(nomad_service=nomad_service)

    assert job == fixture_content("test_create_job.v2")


class PreConfiguredNomadSpawner(NomadSpawner):
    async def job_factory(self, _) -> str:
        return create_job(
            job_data=JobData(
                job_name=self.job_name,
                username=self.user.name,
                notebook_name=self.name,
                service_provider=self.service_provider,
                service_name=self.service_name,
                env=self.get_env(),
                args=self.get_args(),
                image="jupyter/minimal-notebook",
                datacenters=["dc1", "dc2"],
                memory=512,
            ),
            job_template_path=self.job_template_path,
        )


@pytest.mark.asyncio
async def test_spawner_job_factory(user, hub, config):
    spawner = PreConfiguredNomadSpawner(user=user, hub=hub, config=config)

    # is generated in the spawners start method
    spawner.notebook_id = "123"

    nomad_service = Mock()
    job = await spawner.job_factory(nomad_service)

    assert job == fixture_content("test_create_job.v2")


def test_name_rendering_default(user, hub, config):
    # reset to base as fixture uses different base name
    config.NomadSpawner.base_job_name = "jupyterhub-notebook"

    spawner = NomadSpawner(user=user, hub=hub, config=config)

    spawner.notebook_id = "123"

    assert spawner._render_name_template() == "jupyterhub-notebook-123"


def test_name_rendering_with_custom_template(user, hub, config):
    config.NomadSpawner.name_template = "{{username}}-{{servername}}"

    # easier than patching or creating an orm spawner
    class NamedSpawner(NomadSpawner):
        name: str = "testing-server"

    spawner = NamedSpawner(user=user, hub=hub, config=config)

    spawner.notebook_id = "123"

    assert spawner._render_name_template() == "myname-testing-server"
