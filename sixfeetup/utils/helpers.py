import logging
from Testing.makerequest import makerequest
from Products.CMFCore.utils import getToolByName
from Products.GenericSetup.upgrade import _upgrade_registry
from Products.GenericSetup.registry import _profile_registry
from Products.GenericSetup.interfaces import IFilesystemImporter
from Products.CMFPlone.utils import base_hasattr

logger = logging.getLogger(__name__)

def updateCatalog(site):
    """Update the catalog
    """
    logger.info('****** updateCatalog BEGIN ******')
    pc = getToolByName(site, 'portal_catalog')
    pc.refreshCatalog()
    logger.info('****** updateCatalog END ******')

def updateSecurity(site):
    """Run the update security on the workflow tool"""
    logger.info('****** updateSecurity BEGIN ******')
    wtool = getToolByName(site, 'portal_workflow')
    wtool.updateRoleMappings()
    logger.info('****** updateSecurity END ******')

def runUpgradeSteps(site, profile_id):
    """run the upgrade steps for the given profile_id in the form of:
    
    profile-<package_name>:<profile_name>
    
    example:
    
    profile-my.package:default
    
    Basically this is the code from GS.tool.manage_doUpgrades() in step
    form.  Had to extract the code because it was doing a redirect back to the
    upgrades form in the GS tool.
    """
    setup_tool = getToolByName(site, 'portal_setup')
    logger.info('****** runUpgradeSteps BEGIN ******')
    upgrade_steps = setup_tool.listUpgrades(profile_id)
    steps_to_run = []
    for step in upgrade_steps:
        if isinstance(step, list):
            # this is a group of steps
            for new_step in step:
                steps_to_run.append(new_step['step'].id)
        else:
            steps_to_run.append(step['step'].id)
    
    #################
    # from GS tool...
    ##################
    for step_id in steps_to_run:
        step = _upgrade_registry.getUpgradeStep(profile_id, step_id)
        if step is not None:
            step.doStep(setup_tool)
            msg = "Ran upgrade step %s for profile %s" % (step.title,
                                                          profile_id)
            logger.info(msg)

    # XXX should be a bit smarter about deciding when to up the
    #     profile version
    profile_info = _profile_registry.getProfileInfo(profile_id)
    version = profile_info.get('version', None)
    if version is not None:
        setup_tool.setLastVersionForProfile(profile_id, version)

    logger.info('****** runUpgradeSteps END ******')

def publishEverything(site, path=None, transition='published'):
    """Publishes all content that has the given transition
    
    Pass in a path to publish the contents of a specific section.  The path is
    relative to the root.  If your site id is Plone and you pass in
    /foo/bar/baz the path will end up being /Plone/foo/bar/baz
    """
    pc = getToolByName(site, 'portal_catalog')
    portal = site.portal_url.getPortalObject()
    if path is None:
        path = '/'
    else:
        path = "/%s%s" % (portal.id, path)
    results = pc(path=path)
    for result in results:
        obj = result.getObject()
        try:
            obj.portal_workflow.doActionFor(
                obj,
                transition,
                comment='Content published automatically'
            )
        except:
            logger.debug("\ncouldn't publish %s\n**********\n" % obj.Title())

def runMigrationProfile(context, profile_id, structure=False):
    """Run a migration profile as an upgrade step.  It is important to pass in
    the context that is given to the upgrade step method here.  We have to do
    some craziness to make the structure work properly.
    
    profile_id in the form::
    
      profile-<package_name>:<profile_name>
    
    example::
    
      profile-my.package:migration-2008-09-23
    
    If structure is True then it will do some special magic for a profile that
    has a structure folder.
    """
    if structure:
        import_context = context._getImportContext(profile_id)
        site = import_context.getSite()
        IFilesystemImporter(site).import_(import_context, 'structure', True)
    else:
        site = context.getParentNode()
        setup_tool = getToolByName(site, 'portal_setup')
        setup_tool.runAllImportStepsFromProfile(profile_id)

def clearLocks(site, path=None):
    """Little util method to clear locks recursively on a given path
    
    Pass in a path to remove locks of a specific section.  If your site id is
    Plone and you pass in /foo/bar/baz the path will end up being 
    /Plone/foo/bar/baz
    """
    msg = '****** claering all locks for %s in %s ******' % (path, site.id)
    logger.info(msg)
    pu = getToolByName(site, 'portal_url')
    portal = pu.getPortalObject()
    pc = getToolByName(site, 'portal_catalog')
    if path is None:
        path = '/'
    else:
        path = "/%s%s" % (portal.id, path)
    for item in pc(path=path):
        obj_path = '/'.join(item.getObject().getPhysicalPath())
        lock_info = '%s/@@plone_lock_info' % obj_path
        locked = portal.restrictedTraverse(lock_info).is_locked()
        if locked:
            lock_ops = '%s/@@plone_lock_operations' % obj_path
            portal.restrictedTraverse(lock_ops).force_unlock(redirect=False)

def addUserAccounts(site, member_dicts=[]):
    """Add user accounts into the system
    
    Member dictionaries are in the following format::
    
      {
        'id': 'joeblow',
        'password': '12345'
        'roles': ['Manager', 'Member'],
        'properties': {
          'email': 'joe@example.com',
          'fullname': 'Joe Blow',
          'username': 'joeblow',
         }
      }
    
    Additional properties can be added in the properties item and will
    be passed along to the registration tool.
    """
    rtool = getToolByName(site, 'portal_registration')
    rta = rtool.addMember
    for mem in member_dicts:
        try:
            rta(
                id=mem['id'],
                password=mem['password'],
                roles=mem['roles'],
                properties=mem['properties'],
            )
        except ValueError:
            msg = '\nlogin id %s is already taken...\n*********\n' % mem['id']
            logger.debug(msg)

def addRememberUserAccounts(site,
                            member_dicts=[],
                            initial_transition="register_private",
                            send_emails=False):
    """Add remember user accounts into the system
    
    Member dictionaries are in the following format::
    
      {
        'id': 'joeblow',
        'fullname': 'Joe Blow',
        'email': 'joe@example.com',
        'password': '12345',
        'confirm_password': '12345',
        'roles': ['Manager'],
      }
    
    You can pass in more 'fieldName': 'values' in the dictionary, they will be
    passed on to processForm.
    
    initial_transition is the member workflow transition you want to run on 
    the members
    
    If send_emails is True then registration emails will be sent out to the users
    """
    utool = getToolByName(site, 'portal_url')
    portal = utool.getPortalObject()
    # store the current prop
    current_setting = portal.validate_email
    if not send_emails:
        # Turn off email validation
        portal.validate_email = 0
    mdata = getToolByName(site, 'portal_memberdata')
    wftool = getToolByName(site, 'portal_workflow')
    existing_members = mdata.contentIds()
    for mem in member_dicts:
        if mem['id'] not in existing_members:
            mdata.invokeFactory('Member', id=mem['id'])
            new_member = getattr(mdata, mem['id'])
            # remove id as it's already set
            del mem['id']
            # finalize creation of the member
            new_member.processForm(values=mem)
            # now we can register the member since it is 'valid'
            # XXX this may be specific to the approval workflow...
            wftool.doActionFor(new_member, initial_transition)
            # reindex again to update the state info in the catalog
            new_member.reindexObject()
        else:
            msg = '\nlogin id %s is already taken...\n*********\n' % mem['id']
            logger.debug(msg)
    # but the property back
    portal.validate_email = current_setting

def updateSchema(site,
                 update_types=[],
                 update_all=False,
                 remove_inst_schemas=True):
    """Update archetype schemas for specific types
    
    The update types is a list of strings like the following::
    
      <product_or_package>.<meta_type>
    
    Examples::
    
      ATContentTypes.ATDocument
      my.package.SomeType
    """
    portal_obj = getToolByName(site, 'portal_url').getPortalObject()
    portal = makerequest(portal_obj)
    req = portal.REQUEST
    req.form['update_all'] = update_all
    req.form['remove_instance_schemas'] = remove_inst_schemas
    for obj_type in update_types:
        req.form[obj_type] = True
    portal.archetype_tool.manage_updateSchema(req)

def setPolicyOnObject(obj, policy_in=None, policy_below=None):
    """Set the placeful workflow policy on an object
    
    obj is the object we want to set the policy on
    
    policy_in is the policy set only on the obj
    
    policy_below is the policy set on all the items below obj
    """
    placeful_workflow = getToolByName(obj, 'portal_placeful_workflow')
    if not base_hasattr(obj, '.wf_policy_config'):
        obj.manage_addProduct['CMFPlacefulWorkflow'].manage_addWorkflowPolicyConfig()
        config = placeful_workflow.getWorkflowPolicyConfig(obj)
        if policy_in is not None:
            config.setPolicyIn(policy=policy_in)
        if policy_below is not None:
            config.setPolicyBelow(policy=policy_below)
