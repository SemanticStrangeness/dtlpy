import json
import logging
import os
from typing import List, Optional

from .. import exceptions, entities, services, miscellaneous

logger = logging.getLogger(name='dtlpy')


class Dpks:
    def __init__(self, client_api: services.ApiClient, project: entities.Project = None):
        self._client_api = client_api
        self._project = project

    @property
    def project(self) -> Optional[entities.Project]:
        return self._project

    @project.setter
    def project(self, project: entities.Project):
        if not isinstance(project, entities.Project):
            raise ValueError('Must input a valid Project entity')
        self._project = project

    def init(self, directory: str = None, name: str = None, description: str = None,
             categories: List[str] = None, icon: str = None, scope: str = None):
        """
        Initialize a dpk project with the specified projects.

        :param str directory: the directory where to initialize the project
        :param str name: the name of the dpk.
        :param str description: the description of the dpk.
        :param str categories: the categories of the dpk.
        :param str icon: the icon of the dpk.
        :param str scope: the scope of the dpk.

        ** Example **
        .. code-block:: python
            dl.dpks.init(name='Hello World', description='A description of the dpk', categories=['starter', 'advanced'],
                        icon='path_to_icon', scope='organization')
        """
        if directory is None:
            directory = os.getcwd()
        dpk = entities.Dpk.from_json({
            'name': miscellaneous.JsonUtils.get_if_absent(name),
            'description': miscellaneous.JsonUtils.get_if_absent(description),
            'categories': miscellaneous.JsonUtils.get_if_absent(categories),
            'icon': miscellaneous.JsonUtils.get_if_absent(icon),
            'scope': miscellaneous.JsonUtils.get_if_absent(scope, 'organization')
        }, self._client_api, entities.Project.from_json({}, self._client_api, False))

        with open(os.path.join(directory, 'app.json'), 'w') as json_file:
            json_file.write(json.dumps(dpk.to_json(), indent=4))
        os.mkdir(os.path.join(directory, 'src'))
        os.mkdir(os.path.join(directory, 'src', 'functions'))
        os.mkdir(os.path.join(directory, 'src', 'ui'))
        os.mkdir(os.path.join(directory, 'src', 'ui', 'panels'))

    # noinspection PyMethodMayBeStatic
    def pack(self, directory: str = None, name: str = None) -> str:
        """
        :param str directory: optional - the project to pack, if not specified use the current project,
        :param str name: optional - the name of the dpk file.
        :return the path of the dpk file

        **Example**

        .. code-block:: python
            filepath = dl.apps.pack(directory='/my-current-project', name='project-name')
        """
        # create/get .dataloop dir
        cwd = os.getcwd()
        dl_dir = os.path.join(cwd, '.dataloop')
        if not os.path.isdir(dl_dir):
            os.mkdir(dl_dir)
        if directory is None:
            directory = cwd

        # get dpk name
        if name is None:
            name = os.path.basename(directory)

        with open(os.path.join(directory, 'app.json'), 'r') as file:
            app_json = json.load(file)
        version = app_json.get('version', None)
        if version is None:
            logger.warning('No Version specified, setting to 1.0.0')
            version = '1.0.0'
        # create/get dist folder
        dpk_filename = os.path.join(dl_dir, '{}_{}.dpk'.format(name, version))

        if not os.path.isdir(directory):
            raise exceptions.PlatformException(error='400', message='Not a directory: {}'.format(directory))

        try:
            directory = os.path.abspath(directory)
            # create zipfile
            miscellaneous.Zipping.zip_directory(zip_filename=dpk_filename,
                                                directory=directory,
                                                ignore_directories=['artifacts']
                                                )
            return dpk_filename
        except Exception:
            logger.error('Error when packing:')
            raise

    def pull(self, dpk_id: str = None, dpk_name: str = None, local_path=None) -> str:
        """
        Pulls the app from the platform as dpk file.

        Note: you must pass either dpk_name or dpk_id to the function.
        :param str dpk_id: the name of the dpk.
        :param str dpk_name: the id of the dpk.
        :param local_path: the path where you want to install the dpk file.
        :return local path where the package pull

        **Example**
        ..code-block:: python
            path = dl.dpks.pull(dpk_name='my-app')
        """
        dpk = self.get(dpk_id=dpk_id, dpk_name=dpk_name)
        if local_path is None:
            local_path = os.path.join(
                services.service_defaults.DATALOOP_PATH,
                "dpks",
                dpk.name,
                str(dpk.version))

        dpk.codebase.from_json(client_api=self._client_api, _json=dpk.codebase.to_json()).unpack(local_path)
        return local_path

    # noinspection DuplicatedCode
    def __get_by_name(self, dpk_name: str):
        filters = entities.Filters(field='name',
                                   values=dpk_name,
                                   resource=entities.FiltersResource.DPK,
                                   use_defaults=False)
        dpks = self.list(filters=filters)
        if dpks.items_count == 0:
            raise exceptions.PlatformException(
                error='404',
                message='Dpk not found. Name: {}'.format(dpk_name))
        elif dpks.items_count > 1:
            raise exceptions.PlatformException(
                error='400',
                message='More than one dpk found by the name of: {}'.format(dpk_name))
        return dpks.items[0]

    def publish(self, dpk: entities.Dpk = None) -> entities.Dpk:
        """
        Upload a dpk entity to the dataloop platform.

        :param entities.Dpk dpk: the dpk to publish
        :return the published dpk
        :rtype dl.entities.Dpk

        **Example**

        .. code-block:: python
            published_dpk = dl.dpks.publish()
        """

        if dpk is None:
            if not os.path.exists(os.path.abspath('app.json')):
                raise exceptions.PlatformException(error='400',
                                                   message='app.json file must be exists in order to publish a dpk')
            with open('app.json', 'r') as f:
                json_file = json.load(f)
            dpk = entities.Dpk.from_json(json_file, self._client_api, self.project)

        dpk.codebase = self.project.codebases.pack(directory=os.getcwd(),
                                                   name=dpk.display_name,
                                                   extension='dpk',
                                                   ignore_directories=['artifacts'])

        success_pack, response_pack = self._client_api.gen_request(req_type='post',
                                                                   json_req=dpk.to_json(),
                                                                   path='/app-registry')
        if not success_pack:
            raise exceptions.PlatformException(error='400', message=f"Couldn't publish the app, {response_pack}")

        return entities.Dpk.from_json(response_pack.json(), self._client_api, dpk.project)

    def delete(self, dpk_id: str) -> bool:
        """
        Delete the dpk from the app store.

        Note: after removing the dpk, you cant get it again, it's advised to pull it first.

        :param str dpk_id: the id of the dpk.
        :return whether the operation ran successfully
        :rtype bool
        """
        success, response = self._client_api.gen_request(req_type='delete', path=f'app-registry/{dpk_id}')
        if success:
            logger.info('Deleted dpk successfully')
        else:
            raise exceptions.PlatformException(error='400', message="Couldn't delete the dpk from the store")
        return success

    def revisions(self, dpk_id: str) -> List[str]:
        """
        returns the available versions of the dpk.

        :param str dpk_id: the id of the dpk.
        :return the available versions of the dpk.

        ** Example **
        ..code-block:: python
            versions = dl.dpks.revisions(dpk_id='id')
        """
        if dpk_id is None:
            raise exceptions.PlatformException(error='400', message='You must provide dpk_id')
        success, response = self._client_api.gen_request(req_type='post',
                                                         path="app-registry/{}/revisions".format(dpk_id))
        if not success:
            raise exceptions.PlatformException(response)
        json_list = response.json()
        return json.loads(json_list)

    def list(self, filters: entities.Filters = None) -> entities.PagedEntities:
        """
        List the available dpks.

        :param entities.Filters filters: the filters to apply on the list
        :return a paged entity representing the list of dpks.

        ** Example **
        .. code-block:: python
            dpks = dl.dpks.list()
        """
        if filters is None:
            filters = entities.Filters(resource=entities.FiltersResource.DPK)
        elif not isinstance(filters, entities.Filters):
            raise exceptions.PlatformException(error='400',
                                               message='Unknown filters type: {!r}'.format(type(filters)))
        elif filters.resource != entities.FiltersResource.DPK:
            raise exceptions.PlatformException(
                error='400',
                message='Filters resource must to be FiltersResource.DPK. Got: {!r}'.format(filters.resource))

        paged = entities.PagedEntities(items_repository=self,
                                       filters=filters,
                                       page_offset=filters.page,
                                       page_size=filters.page_size,
                                       client_api=self._client_api)
        paged.get_page()
        return paged

    def _list(self, filters: entities.Filters):
        url = 'app-registry/query'

        # request
        success, response = self._client_api.gen_request(req_type='post',
                                                         path=url,
                                                         json_req=filters.prepare())
        if not success:
            raise exceptions.PlatformException(response)
        return response.json()

    def get(self, dpk_id: str = None, dpk_name: str = None) -> entities.Dpk:
        """
        Get a specific dpk from the platform.

        Note: you must pass either dpk_id or dpk_name.

        :param str dpk_id: the id of the dpk to get.
        :param str dpk_name: the name of the dpk to get.
        :return the entitiy of the dpk
        :rtype entities.Dpk

        ** Example **
        ..coed-block:: python
            dpk = dl.dpks.get(dpk_name='name')
        """
        if dpk_id is None and dpk_name is None:
            raise exceptions.PlatformException(error='400', message='You must provide an identifier')
        if dpk_id is not None:
            url = '/app-registry/{}'.format(dpk_id)

            # request
            success, response = self._client_api.gen_request(req_type='get',
                                                             path=url)
            if not success:
                raise exceptions.PlatformException(response)

            dpk = entities.Dpk.from_json(_json=response.json(),
                                         client_api=self._client_api,
                                         project=self.project,
                                         is_fetched=False)
        else:
            dpk = self.__get_by_name(dpk_name)

        return dpk
