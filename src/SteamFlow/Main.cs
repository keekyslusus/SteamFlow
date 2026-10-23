using System.Windows.Controls;
using Flow.Launcher.Plugin;

namespace SteamFlow;

public sealed class Main : IAsyncPlugin, IContextMenu, IPluginI18n, IReloadable, ISettingProvider, IResultUpdated, IDisposable
{
    private PluginInitContext context = null!;
    private PluginServices services = null!;

    public event ResultUpdatedEventHandler? ResultsUpdated;

    public Task InitAsync(PluginInitContext context)
    {
        this.context = context;
        services = CompositionRoot.Create(context);
        services.Library.Reload();
        services.Store.WarmUp();
        services.StoreImages.WarmUp();
        services.OwnedGames.WarmUp();
        services.Profile.WarmUp();
        services.Wishlist.WarmUp();
        return Task.CompletedTask;
    }

    public Task<List<Result>> QueryAsync(Query query, CancellationToken token) =>
        services.Queries.QueryAsync(
            query,
            token,
            results => ResultsUpdated?.Invoke(this, new ResultUpdatedEventArgs { Query = query, Results = results, Token = token }));

    public List<Result> LoadContextMenus(Result selectedResult) =>
        selectedResult.ContextData is ResultMenu menu ? menu.Build() : [];

    public void ReloadData() => services.Library.Reload();

    public Control CreateSettingPanel() => services.CreateSettingsPanel();

    public string GetTranslatedPluginTitle() => context.API.GetTranslation("steamflow_plugin_title");

    public string GetTranslatedPluginDescription() => context.API.GetTranslation("steamflow_plugin_description");

    public void Dispose() => services?.Dispose();
}
