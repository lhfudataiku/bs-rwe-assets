from dku_utils.type_checking import DSSProject, check_object_is_project


def get_folder_item_names(project, folder_id):
    folder = project.get_managed_folder(folder_id)
    folder_items = [item['path'] for item in folder.list_contents().get('items', [])]
    return folder_items

def check_item_in_folder(project, folder_id, item_name):
    check_object_is_project(project)
    folder_items = get_folder_item_names(project, folder_id)
    return item_name in folder_items