"""Serviço de workloads isolado; composição e UI pertencem às ondas seguintes."""

from .service import ApprovedTemplate, WorkloadError, WorkloadService
from .build import BuildService, DockerImageBuilder
from .docker_runtime import DockerWorkloadRuntime
from .manifest import parse_manifest
from .proxy import WorkloadProxy
from .proxy_policy import ProxyRoute
from .template_registry import TemplateRegistry

__all__ = ['ApprovedTemplate', 'WorkloadError', 'WorkloadService', 'BuildService',
           'DockerImageBuilder', 'DockerWorkloadRuntime', 'parse_manifest',
           'WorkloadProxy', 'ProxyRoute', 'TemplateRegistry']
